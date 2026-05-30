"""Load a synthetic fixture repo into a db via the REAL chunk+embed path, so the
eval exercises the actual retrieval stack (just small)."""
from __future__ import annotations

from pathlib import Path

import yaml

_LANG = {".py": "python", ".md": "markdown", ".js": "javascript", ".ts": "typescript", ".go": "go"}


async def load_fixture_repo(db, embedder, fixture_dir: Path, repo_id: str) -> int:
    """Chunk + embed every file under fixture_dir into code_embeddings for repo_id.

    Ensures the embeddings table and correct vector dimension exist first by
    calling EmbeddingService.create_table (idempotent, async-safe). The
    ``code_embeddings`` SQLAlchemy model is created by ``Base.metadata.create_all``
    in the ``async_db`` fixture, but ``create_table`` handles the case where this
    fixture is used outside that context.
    """
    from app.services.knowledge.chunker import CodeChunker
    from app.services.knowledge.embeddings import EmbeddingService

    # Ensure table exists at correct dimension (idempotent).
    await EmbeddingService.create_table(db)

    chunker = CodeChunker()
    total = 0
    for path in sorted(fixture_dir.iterdir()):
        if not path.is_file():
            continue
        content = path.read_text()
        lang = _LANG.get(path.suffix, "text")
        # CodeChunker.chunk_file(content, file_path, language) -> list[CodeChunk]
        chunks = chunker.chunk_file(content, path.name, lang)
        if chunks:
            stored = await embedder.embed_and_store(db, chunks, repo_id=repo_id)
            total += stored
    return total


def load_golden(name: str) -> list[dict]:
    """Read app/evals/golden/<name> -> list of {id, question, repo, expect_files}."""
    golden_path = Path(__file__).parent / "golden" / name
    doc = yaml.safe_load(golden_path.read_text())
    repo = doc["repo"]
    return [
        {"id": q["id"], "question": q["question"], "repo": repo, "expect_files": q["expect_files"]}
        for q in doc["questions"]
    ]
