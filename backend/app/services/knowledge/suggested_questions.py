"""Build grounded starter questions for the dashboard from real repo facts.

Pure on purpose: the input is already-fetched facts (the active repo's name,
whether it has any PRs, the most-populated module path, whether the graph knows
any contributors) and the output is an ordered, deduped list of question
strings. No DB or Neo4j access here, so it is trivially unit-testable and can
never invent a repo or module that doesn't exist — a template is only emitted
when the data backing it is present.
"""

from __future__ import annotations


def build_suggested_questions(
    repo_name: str | None,
    *,
    has_prs: bool = False,
    top_module: str | None = None,
    has_contributors: bool = False,
    max_questions: int = 4,
) -> list[str]:
    if not repo_name:
        return []

    candidates: list[str] = []
    if has_prs:
        candidates.append(f"Summarize this week's PRs in {repo_name}")
    if top_module:
        candidates.append(f"Who knows the most about {top_module}?")
    candidates.append(f"What changed recently in {repo_name}?")
    if has_contributors:
        candidates.append(f"Who are the top contributors to {repo_name}?")

    seen: set[str] = set()
    questions: list[str] = []
    for q in candidates:
        if q not in seen:
            seen.add(q)
            questions.append(q)
    return questions[:max_questions]
