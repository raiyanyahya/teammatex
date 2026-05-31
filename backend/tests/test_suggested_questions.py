"""Unit tests for the grounded dashboard-question builder.

The builder is pure (facts in → question strings out), so these tests pin the
exact behavior without a DB: it never emits a question for data that isn't
there, and it never invents a repo or module.
"""
from app.services.knowledge.suggested_questions import build_suggested_questions


def test_no_repo_returns_empty():
    assert build_suggested_questions(None) == []
    assert build_suggested_questions("") == []


def test_bare_repo_still_offers_the_repo_scoped_question():
    # With no PRs / module / contributors known, only the always-available
    # "what changed recently" question grounds out.
    assert build_suggested_questions("teammatex") == [
        "What changed recently in teammatex?",
    ]


def test_full_facts_produce_all_grounded_questions_in_order():
    qs = build_suggested_questions(
        "teammatex",
        has_prs=True,
        top_module="app/services/agent",
        has_contributors=True,
    )
    assert qs == [
        "Summarize this week's PRs in teammatex",
        "Who knows the most about app/services/agent?",
        "What changed recently in teammatex?",
        "Who are the top contributors to teammatex?",
    ]


def test_questions_only_appear_when_their_data_exists():
    qs = build_suggested_questions("teammatex", has_prs=True)
    assert qs == [
        "Summarize this week's PRs in teammatex",
        "What changed recently in teammatex?",
    ]
    assert all("knows the most" not in q for q in qs)
    assert all("top contributors" not in q for q in qs)


def test_max_questions_caps_the_list():
    qs = build_suggested_questions(
        "teammatex",
        has_prs=True,
        top_module="app",
        has_contributors=True,
        max_questions=2,
    )
    assert qs == [
        "Summarize this week's PRs in teammatex",
        "Who knows the most about app?",
    ]
