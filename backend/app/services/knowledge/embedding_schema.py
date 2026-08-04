"""Single source of truth for the code-embeddings vector dimension.

The pgvector column dimension MUST equal what the configured embedding model
emits, or every insert fails with ``expected N dimensions``. The local default
model (``all-MiniLM-L6-v2``) emits 384; OpenAI ``text-embedding-3-small`` emits
1536. The DB schema was historically hardcoded to 1536, which silently broke the
local path (every insert raised and the error was swallowed → 0 rows stored).

These helpers keep the schema and the model in agreement and let the onboarding
pipeline self-correct a table that was created with the wrong dimension.
"""

from __future__ import annotations

import re

LOCAL_DIM = 384
OPENAI_DIM = 1536


def expected_dim(provider: str) -> int:
    """Dimension the configured provider's model is expected to emit."""
    return LOCAL_DIM if provider == "local" else OPENAI_DIM


def parse_vector_dim(format_type: str | None) -> int | None:
    """Extract N from a Postgres ``vector(N)`` type string, else None."""
    m = re.search(r"vector\((\d+)\)", format_type or "")
    return int(m.group(1)) if m else None


def reconcile_embeddings_dim(conn, target_dim: int) -> str:
    """Ensure ``code_embeddings.embedding`` is ``vector(target_dim)``.

    Embeddings are fully regenerable from the repo, so on a dimension mismatch we
    reset the column rather than try to migrate vectors. Returns one of
    ``"absent"`` (no table yet), ``"ok"`` (already correct), or ``"fixed"``.

    Takes a live SQLAlchemy connection; callers wrap it in a transaction.
    """
    from sqlalchemy import text as t

    row = conn.execute(
        t(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass('code_embeddings') "
            "AND a.attname = 'embedding' AND NOT a.attisdropped"
        )
    ).fetchone()
    if not row:
        return "absent"
    current = parse_vector_dim(row[0])
    if current == target_dim:
        return "ok"
    conn.execute(t("TRUNCATE code_embeddings"))
    conn.execute(t(f"ALTER TABLE code_embeddings ALTER COLUMN embedding TYPE vector({target_dim})"))
    return "fixed"
