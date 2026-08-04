from pathlib import Path

import pytest

from app.evals.engine import aggregate, score_item


def test_hit_at_k_and_reciprocal_rank():
    # expected file at rank 2 → hit@3 true, hit@1 false, rr = 0.5
    r = score_item(ranked=["a.py", "b.py", "c.py"], expect_files=["b.py"], k=3)
    assert r["hit"] is True
    assert r["rank"] == 2
    assert r["rr"] == 0.5

    r1 = score_item(ranked=["a.py", "b.py", "c.py"], expect_files=["b.py"], k=1)
    assert r1["hit"] is False  # not in top-1
    assert r1["rank"] == 2  # rank still reported
    assert r1["rr"] == 0.5


def test_miss_returns_zero_rr_and_no_rank():
    r = score_item(ranked=["a.py", "b.py"], expect_files=["z.py"], k=3)
    assert r["hit"] is False
    assert r["rank"] is None
    assert r["rr"] == 0.0


def test_aggregate_means():
    items = [
        {"hit": True, "rank": 1, "rr": 1.0},
        {"hit": True, "rank": 2, "rr": 0.5},
        {"hit": False, "rank": None, "rr": 0.0},
    ]
    agg = aggregate(items)
    assert agg["count"] == 3
    assert round(agg["hit_rate"], 3) == round(2 / 3, 3)
    assert round(agg["mrr"], 3) == round((1.0 + 0.5 + 0.0) / 3, 3)


@pytest.mark.asyncio
async def test_fixture_retrieval_eval_meets_floor(async_db):
    from app.evals.engine import run_eval
    from app.evals.fixtures import load_fixture_repo, load_golden
    from app.services.knowledge.embeddings import EmbeddingService

    repo_id = "eval-fixture"
    fixture_dir = Path(__file__).parent / "fixtures" / "eval_repo"
    embedder = EmbeddingService()

    await load_fixture_repo(async_db, embedder, fixture_dir, repo_id)
    golden = load_golden("fixture.yaml")
    report = await run_eval(async_db, embedder, golden, k=3)

    # Every question should retrieve its file in the top 3 on this tiny, distinct corpus.
    assert report["summary"]["hit_rate"] >= 0.8, report
    q1 = next(i for i in report["items"] if i["id"] == "q1")
    assert q1["rank"] == 1  # the Stripe question hits its file first


def test_threshold_exit_code():
    from app.evals.__main__ import exit_code_for

    assert exit_code_for(summary={"hit_rate": 0.9}, threshold=0.8) == 0
    assert exit_code_for(summary={"hit_rate": 0.7}, threshold=0.8) == 1
