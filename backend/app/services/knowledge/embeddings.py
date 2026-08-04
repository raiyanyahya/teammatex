import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.config import settings

if TYPE_CHECKING:
    from app.services.knowledge.chunker import CodeChunk

logger = get_logger(__name__)

EMBEDDING_DIM = 384 if settings.embedding_provider == "local" else 1536

_DEFAULT_LOCAL_MODEL = "BAAI/bge-small-en-v1.5"

# fastembed uses Hugging-Face-style IDs, so map the legacy bare sentence-transformers
# names an existing .env may pin onto their fastembed equivalents. Mapping
# all-MiniLM to the fastembed ONNX MiniLM keeps an already-embedded corpus valid
# (same weights → same vectors, no re-embed) while new installs default to bge-small.
_LOCAL_MODEL_ALIASES = {
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
}


def load_local_embedder(model_name: str):
    """Build a fastembed TextEmbedding for `model_name`, normalizing legacy names
    and falling back to the default if the (mis)configured model isn't supported.
    Returns (model, resolved_name)."""
    from fastembed import TextEmbedding

    name = _LOCAL_MODEL_ALIASES.get(model_name, model_name)
    try:
        return TextEmbedding(model_name=name), name
    except ValueError:
        logger.warning(
            "embedding_model_unsupported_fallback", requested=name, using=_DEFAULT_LOCAL_MODEL
        )
        return TextEmbedding(model_name=_DEFAULT_LOCAL_MODEL), _DEFAULT_LOCAL_MODEL


class EmbeddingService:
    # Local embeddings run on fastembed (ONNX) — no PyTorch. The default model,
    # BAAI/bge-small-en-v1.5, beat the old all-MiniLM-L6-v2 on a retrieval bake-off
    # over this codebase (hit@5 1.00 vs 0.89, MRR 0.82 vs 0.75) at the same 384 dims,
    # while dropping the ~2.6 GB torch dependency. BGE is asymmetric: documents and
    # queries get different prefixes, so store via passage_embed and search via
    # query_embed (fastembed applies the right prefix per model).
    _model: object | None = None
    _client: object | None = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            if settings.embedding_provider == "local":
                cls._model, resolved = load_local_embedder(settings.embedding_model)
                logger.info("local_embedding_model_loaded", model=resolved)
            else:
                from openai import AsyncOpenAI

                cls._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return cls._model

    async def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        if settings.embedding_provider == "local":
            return self._embed_local(texts, is_query)
        else:
            return await self._embed_openai(texts)

    def _embed_local(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        model = self.get_model()
        gen = model.query_embed(texts) if is_query else model.passage_embed(texts)
        return [v.tolist() for v in gen]

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key)

        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [d.embedding for d in response.data]

    async def embed_and_store(
        self,
        db: AsyncSession,
        chunks: list["CodeChunk"],
        repo_id: str,
        batch_size: int = 20,
    ) -> int:

        stored = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]
            try:
                vectors = await self.embed(texts)
            except Exception as e:
                logger.error("embedding_failed", error=str(e))
                continue

            for chunk, vector in zip(batch, vectors, strict=False):
                chunk_id = self._chunk_id(repo_id, chunk.file_path, chunk.start_line)
                vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                await db.execute(
                    text(
                        """
                    INSERT INTO code_embeddings (id, repo_id, text, embedding, file_path,
                        start_line, end_line, entity_type, language, entity_name)
                    VALUES (:id, :repo_id, :text, CAST(:embedding AS vector), :file_path,
                        :start_line, :end_line, :entity_type, :language, :entity_name)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        text = EXCLUDED.text
                    """
                    ),
                    {
                        "id": chunk_id,
                        "repo_id": repo_id,
                        "text": chunk.text,
                        "embedding": vector_str,
                        "file_path": chunk.file_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "entity_type": chunk.entity_type,
                        "language": chunk.language,
                        "entity_name": chunk.entity_name,
                    },
                )
                stored += 1

        await db.commit()
        return stored

    async def search(
        self,
        db: AsyncSession,
        query: str,
        repo_id: str | None = None,
        entity_type: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        query_vector = (await self.embed([query], is_query=True))[0]
        vector_str = f"[{', '.join(str(v) for v in query_vector)}]"

        conditions = ["TRUE"]
        params: dict = {"limit": limit, "vector": vector_str}
        if repo_id:
            conditions.append("ce.repo_id = :repo_id")
            params["repo_id"] = repo_id
        if entity_type:
            conditions.append("ce.entity_type = :entity_type")
            params["entity_type"] = entity_type
        if language:
            conditions.append("ce.language = :language")
            params["language"] = language

        where = " AND ".join(conditions)

        result = await db.execute(
            text(
                f"""
            SELECT ce.file_path, ce.start_line, ce.end_line, ce.text,
                   ce.entity_type, ce.language, ce.entity_name,
                   1 - (ce.embedding <=> CAST(:vector AS vector)) AS similarity
            FROM code_embeddings ce
            WHERE {where}
            ORDER BY ce.embedding <=> CAST(:vector AS vector)
            LIMIT :limit
            """
            ),
            params,
        )
        rows = result.fetchall()
        return [
            {
                "file_path": r[0],
                "start_line": r[1],
                "end_line": r[2],
                "text": r[3][:2000],
                "entity_type": r[4],
                "language": r[5],
                "entity_name": r[6],
                "similarity": float(r[7]),
            }
            for r in rows
        ]

    @staticmethod
    def _chunk_id(repo_id: str, file_path: str, start_line: int) -> str:
        raw = f"{repo_id}:{file_path}:{start_line}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    async def create_table(db: AsyncSession) -> None:
        dim = EMBEDDING_DIM
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.execute(
            text(
                f"""
        CREATE TABLE IF NOT EXISTS code_embeddings (
            id VARCHAR(32) PRIMARY KEY,
            repo_id VARCHAR(36),
            text TEXT NOT NULL,
            embedding vector({dim}),
            file_path VARCHAR(1024) NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            entity_type VARCHAR(50),
            language VARCHAR(50),
            entity_name VARCHAR(255)
        )
        """
            )
        )
        # Backfill the column on tables created before repo-scoping existed.
        await db.execute(
            text("ALTER TABLE code_embeddings ADD COLUMN IF NOT EXISTS repo_id VARCHAR(36)")
        )
        await db.commit()

    @staticmethod
    async def create_index(db: AsyncSession) -> None:
        await db.execute(
            text(
                """
        CREATE INDEX IF NOT EXISTS idx_code_embeddings_file
        ON code_embeddings (file_path)
        """
            )
        )
        await db.execute(
            text(
                """
        CREATE INDEX IF NOT EXISTS idx_code_embeddings_entity
        ON code_embeddings (entity_type, language)
        """
            )
        )
        await db.execute(
            text(
                """
        CREATE INDEX IF NOT EXISTS idx_code_embeddings_repo
        ON code_embeddings (repo_id)
        """
            )
        )
        await db.commit()
