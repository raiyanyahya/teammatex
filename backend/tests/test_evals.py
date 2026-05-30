from app.evals.engine import score_item, aggregate


def test_hit_at_k_and_reciprocal_rank():
    # expected file at rank 2 → hit@3 true, hit@1 false, rr = 0.5
    r = score_item(ranked=["a.py", "b.py", "c.py"], expect_files=["b.py"], k=3)
    assert r["hit"] is True
    assert r["rank"] == 2
    assert r["rr"] == 0.5

    r1 = score_item(ranked=["a.py", "b.py", "c.py"], expect_files=["b.py"], k=1)
    assert r1["hit"] is False        # not in top-1
    assert r1["rank"] == 2           # rank still reported
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
