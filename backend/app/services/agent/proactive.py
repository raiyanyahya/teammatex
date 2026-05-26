from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.config import settings
from app.services.integrations.base import IntegrationRegistry
from app.services.llm.provider import LLMProvider

logger = get_logger(__name__)


class StandupGenerator:
    async def generate(self, db: AsyncSession) -> dict:
        from sqlalchemy import select
        from app.models.pr import PR
        from app.models.task import Task

        yesterday = await self._get_prs_since(db, hours=24)
        today_planned = await self._get_active_tasks(db)

        return {
            "name": settings.teammate_name,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "yesterday": self._format_prs(yesterday) if yesterday else "No PR activity.",
            "today": self._format_tasks(today_planned) if today_planned else "Monitoring for new tasks.",
            "blockers": "None",
            "prs": yesterday,
        }

    async def _get_prs_since(self, db: AsyncSession, hours: int) -> list[dict]:
        from sqlalchemy import select
        from app.models.pr import PR

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await db.execute(
            select(PR).where(PR.created_at >= cutoff).order_by(PR.created_at.desc()).limit(10)
        )
        prs = result.scalars().all()
        return [
            {"title": p.title, "status": p.status or "open", "branch": p.branch}
            for p in prs
        ]

    async def _get_active_tasks(self, db: AsyncSession) -> list[dict]:
        from sqlalchemy import select
        from app.models.task import Task

        result = await db.execute(
            select(Task).where(Task.status.in_(["open", "in_progress"])).order_by(Task.updated_at.desc()).limit(10)
        )
        tasks = result.scalars().all()
        return [
            {"title": t.title, "status": t.status, "priority": t.priority or "normal"}
            for t in tasks
        ]

    def _format_prs(self, prs: list[dict]) -> str:
        if not prs:
            return "No PR activity."
        lines = [f"• {p.get('title', 'PR')} — {p.get('status', 'open')}" for p in prs]
        return "\n".join(lines)

    def _format_tasks(self, tasks: list[dict]) -> str:
        if not tasks:
            return "No active tasks."
        lines = [f"• {t.get('title', 'Task')} [{t.get('status', 'pending')}]" for t in tasks]
        return "\n".join(lines)


class DocumentationGenerator:
    async def generate_module_docs(
        self, module_name: str, code_summary: str, entities: list[dict]
    ) -> str:
        prompt = f"""Generate comprehensive documentation for the module '{module_name}'.

Code summary: {code_summary}

Entities in this module:
{self._format_entities(entities)}

Generate a README.md with:
1. Module overview and purpose
2. Architecture and design decisions
3. API reference for public functions/classes
4. Usage examples
5. Dependencies
"""
        return await LLMProvider.simple_prompt(
            system="You are a technical writer. Generate clean, accurate documentation in markdown.",
            user=prompt,
        )

    async def generate_architecture_overview(self, repo_name: str, modules: list[dict]) -> str:
        prompt = f"""Generate an architecture overview for '{repo_name}'.

Modules:
{self._format_modules(modules)}

Include:
1. High-level architecture diagram description
2. Module responsibilities
3. Data flow between modules
4. Key design patterns
5. Technology choices
"""
        return await LLMProvider.simple_prompt(
            system="You are a software architect documenting a system.",
            user=prompt,
        )

    def _format_entities(self, entities: list[dict]) -> str:
        lines = []
        for e in entities:
            name = e.get("name", "unknown")
            kind = e.get("kind", "entity")
            sig = e.get("signature", "")
            lines.append(f"- [{kind}] {name}{sig}")
        return "\n".join(lines[:50])

    def _format_modules(self, modules: list[dict]) -> str:
        lines = []
        for m in modules:
            lines.append(f"- {m.get('module', 'unknown')}: {m.get('file_count', 0)} files, {m.get('function_count', 0)} functions")
        return "\n".join(lines[:30])


class ReleaseNotesGenerator:
    async def generate(self, repo_name: str, commits: list[dict], previous_tag: str | None = None) -> str:
        commit_text = "\n".join(
            f"- {c.get('hash', '')[:8]} {c.get('message', '')}"
            for c in commits[:100]
        )

        prompt = f"""Generate release notes for '{repo_name}'.
{f'Since tag: {previous_tag}' if previous_tag else 'All commits:'}

Commits:
{commit_text}

Categorize into:
- 🚀 Features
- 🐛 Bug Fixes
- ⚠️ Breaking Changes
- 📦 Dependency Updates
- 🔧 Internal Refactors

Include a summary at the top and migration guide for breaking changes.
"""
        return await LLMProvider.simple_prompt(
            system="You generate clean, well-structured release notes in markdown.",
            user=prompt,
        )


class TestGenerator:
    async def generate_tests(
        self, code: str, language: str, function_name: str, test_framework: str = "pytest",
    ) -> str:
        prompt = f"""Generate comprehensive unit tests for the following {language} function.

Function name: {function_name}
Test framework: {test_framework}

Code to test:
```{language}
{code}
```

Generate tests that cover:
1. Happy path
2. Edge cases (null, empty, boundary values)
3. Error cases (invalid input, exceptions)
4. All code branches

Return only the test code.
"""
        return await LLMProvider.simple_prompt(
            system=f"You are a {language} test engineer. Write thorough, idiomatic tests.",
            user=prompt,
            temperature=0.1,
        )

    async def analyze_gaps(self, code_summary: str, existing_tests: list[str]) -> dict:
        prompt = f"""Analyze test coverage gaps.

Code summary:
{code_summary}

Existing tests:
{self._format_existing_tests(existing_tests)}

Return JSON with:
- uncovered_functions: list of functions with no tests
- risky_areas: areas with high complexity but low coverage
- suggestions: 3-5 specific test recommendations
"""
        result = await LLMProvider.simple_prompt(
            system="You are a test coverage analyst. Return JSON only.",
            user=prompt,
            temperature=0.1,
        )
        return {"analysis": result}

    def _format_existing_tests(self, tests: list[str]) -> str:
        return "\n".join(f"- {t}" for t in tests[:50])
