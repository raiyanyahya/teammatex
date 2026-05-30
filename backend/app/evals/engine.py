"""Deterministic retrieval eval: score a ranked list of file paths against the
expected source file(s) for a question. Scores the retrieval primitive directly
(EmbeddingService.search), so results are reproducible and token-free."""
from __future__ import annotations


def _unique(paths: list[str]) -> list[str]:
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def score_item(ranked: list[str], expect_files: list[str], k: int) -> dict:
    """ranked: file paths ordered best-first (may repeat; deduped here)."""
    uniq = _unique(ranked)
    expect = set(expect_files)
    rank = None
    for i, p in enumerate(uniq, start=1):
        if p in expect:
            rank = i
            break
    return {
        "hit": rank is not None and rank <= k,
        "rank": rank,
        "rr": (1.0 / rank) if rank else 0.0,
    }


def aggregate(items: list[dict]) -> dict:
    n = len(items) or 1
    return {
        "count": len(items),
        "hit_rate": sum(1 for it in items if it["hit"]) / n,
        "mrr": sum(it["rr"] for it in items) / n,
    }


async def run_eval(db, embedder, golden: list[dict], k: int = 3) -> dict:
    """golden: [{"id", "question", "repo", "expect_files": [...]}]. Returns a
    report: {"items": [...per question...], "summary": aggregate(...)}."""
    items = []
    for q in golden:
        results = await embedder.search(db, query=q["question"], repo_id=q["repo"], limit=max(k * 3, 10))
        ranked = [r["file_path"] for r in results]
        scored = score_item(ranked, q["expect_files"], k)
        items.append({"id": q["id"], "question": q["question"], **scored, "top": _unique(ranked)[:k]})
    return {"items": items, "summary": aggregate([{"hit": i["hit"], "rr": i["rr"]} for i in items])}
