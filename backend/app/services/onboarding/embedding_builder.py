from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.services.knowledge.chunker import CodeChunker
from app.services.knowledge.embeddings import EmbeddingService

logger = get_logger(__name__)


class EmbeddingBuilder:
    MAX_FILES = 5000
    BATCH_SIZE = 20

    async def build(
        self,
        db: AsyncSession,
        clone_path: str,
        repo_id: str,
    ) -> dict:
        await EmbeddingService.create_table(db)
        await EmbeddingService.create_index(db)

        chunker = CodeChunker()
        embedder = EmbeddingService()
        all_chunks: list = []

        root = Path(clone_path)
        files_scanned = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file() or ".git" in file_path.parts:
                continue
            if files_scanned >= self.MAX_FILES:
                logger.warning("max_files_reached", limit=self.MAX_FILES)
                break

            ext = file_path.suffix.lower()
            lang_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java",
            }
            language = lang_map.get(ext)
            if not language:
                continue

            fpath = str(file_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            if not content.strip():
                continue

            chunks = chunker.chunk_file(content, fpath, language)
            all_chunks.extend(chunks)
            files_scanned += 1

        stored = await embedder.embed_and_store(db, all_chunks, repo_id, batch_size=self.BATCH_SIZE)

        logger.info(
            "embeddings_built",
            repo_id=repo_id,
            files_scanned=files_scanned,
            chunks=len(all_chunks),
            stored=stored,
        )

        return {
            "files_scanned": files_scanned,
            "chunks_created": len(all_chunks),
            "chunks_stored": stored,
        }
