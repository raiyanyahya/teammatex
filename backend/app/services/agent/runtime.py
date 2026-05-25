import asyncio
import json
import re as _re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path as _Path
from typing import Any, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.config import settings
from app.services.agent.guardrails import guardrails, GuardResult
from app.services.agent.memory import MemoryManager
from app.services.agent.prompts import (
    PERSONA_PROMPTS,
    TOOL_USE_SYSTEM_PROMPT,
    PLANNING_PROMPT,
    CODE_GENERATION_PROMPT,
    SELF_REVIEW_PROMPT,
)
from app.services.agent.rag import RAGPipeline
from app.services.agent.tools import ToolRegistry, tool_registry
from app.services.agent.confidence import ConfidenceTier, is_low_confidence, flag_if_low
from app.services.agent.cost_tracker import log_cost, log_audit
from app.services.llm.provider import LLMProvider


def _get_github_token() -> str:
    from app.config import settings as _s
    token = _s.github_client_secret or _s.github_webhook_secret
    if not token:
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"))
            with engine.connect() as conn:
                row = conn.execute(text("SELECT value FROM app_config WHERE key = 'github_token'")).fetchone()
                if row and row[0]:
                    import json as _json
                    data = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    token = data.get("token", "")
            engine.dispose()
        except Exception:
            pass
    return token

logger = get_logger(__name__)

def _is_safe_path(path: str) -> bool:
    # Full access inside the container (the container is the sandbox, and
    # run_command is already unrestricted). Any concrete path is allowed.
    return bool(path and str(path).strip())


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentContext:
    repo_id: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    task_id: str | None = None
    files_modified: list[str] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    db: AsyncSession | None = None
    context_confidence: float = 0.0
    low_confidence_count: int = 0


class AgentRuntime:
    def __init__(self):
        self.memory = MemoryManager()
        self.rag = RAGPipeline()
        self.tools = tool_registry
        self.llm = LLMProvider()

    def _get_persona_prompt(self) -> str:
        persona = settings.teammate_persona
        template = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["helpful_senior_dev"])
        return template.format(name=settings.teammate_name)

    # Tools the chat agent is allowed to drive. A small, powerful set: a real
    # shell does the git/gh/test work, so there are no scripted git tools and no
    # (currently empty) graph/semantic tools to waste turns on.
    CORE_TOOLS = {
        "read_file", "write_file", "edit_file", "list_directory",
        "glob_search", "grep_search", "run_command", "web_search",
    }

    def _curated_tools(self) -> list[dict]:
        return [t for t in self.tools.get_openai_tools()
                if t["function"]["name"] in self.CORE_TOOLS]

    async def _github_token_present(self, db: AsyncSession | None) -> bool:
        from app.config import settings as _s
        if _s.github_client_secret or _s.github_webhook_secret:
            return True
        if db is None:
            return False
        try:
            from sqlalchemy import select
            from app.models.app_config import AppConfig
            result = await db.execute(select(AppConfig).where(AppConfig.key == "github_token"))
            row = result.scalar_one_or_none()
            if row and row.value:
                data = json.loads(row.value) if isinstance(row.value, str) else row.value
                return bool(data.get("token"))
        except Exception:
            pass
        return False

    def _build_system_prompt(self, context: str, env_block: str,
                             github_connected: bool) -> str:
        name = settings.teammate_name
        git_caps = (
            "git is installed and configured, and the `gh` GitHub CLI is installed "
            "and authenticated — so you can branch, edit, commit, push, and open "
            "real pull requests entirely on your own by running commands."
            if github_connected else
            "git is installed for local work; pushing or opening a PR needs a GitHub "
            "token, so if the user asks for a PR and one isn't configured, tell them "
            "to add a token in Settings."
        )
        parts = [
            f"You are {name}, an autonomous software-engineering teammate working on "
            f"the user's codebases. You are NOT Claude, GPT, or any specific model.",
            "",
            "You have a real Linux shell with full access via the run_command tool, "
            "plus tools to read/write/edit files, search code (grep/glob), and search "
            f"the live web. {git_caps}",
            "",
            "Work like a senior engineer: investigate first (read, grep, ls), make the "
            "change, verify it where you can (build/lint/test), then deliver. Decide HOW "
            "to do a task yourself and just do it — don't ask permission for routine "
            "steps, and never write tool calls as plain text. When finished, reply with "
            "a short plain-text summary of what you did, including any PR links.",
            "",
            env_block or "",
        ]
        if context:
            parts += ["", "Relevant code context:", context]
        return "\n".join(parts)

    async def chat(
        self, db: AsyncSession, user_message: str,
        repo_id: str | None = None, conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        from litellm import acompletion
        import json

        ctx = AgentContext(repo_id=repo_id, db=db)

        # Self-heal git/gh auth so a token added via Settings works without an
        # API restart (otherwise the agent thrashes on push with no credentials).
        try:
            from app.services.agent.git_setup import ensure_gh_ready
            await ensure_gh_ready(db)
        except Exception:
            pass

        try:
            context = await self.rag.retrieve_context(db, user_message, repo_id)
        except Exception:
            context = ""

        try:
            from app.services.agent.environment import build_environment_context
            env_block = await build_environment_context(db)
        except Exception:
            env_block = ""

        github_connected = await self._github_token_present(db)
        system_prompt = self._build_system_prompt(context, env_block, github_connected)

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            for msg in conversation_history[-30:]:
                if msg.get("role") in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        tools = self._curated_tools()

        usage = {"in": 0, "out": 0, "calls": 0,
                 "provider": "deepseek", "model": "deepseek-v4-flash"}

        async def llm_call(msgs, tls):
            providers = await LLMProvider._get_available_providers()
            for provider, model, key in providers:
                try:
                    actual_model = LLMProvider._get_model_name(provider, model)
                    resp = await acompletion(
                        model=actual_model, messages=msgs, api_key=key,
                        temperature=0.2, max_tokens=2000, tools=tls,
                    )
                    usage["calls"] += 1
                    usage["provider"], usage["model"] = provider, model
                    if resp.usage:
                        usage["in"] += resp.usage.prompt_tokens or 0
                        usage["out"] += resp.usage.completion_tokens or 0
                    return resp
                except Exception as e:
                    logger.warning("llm_call_failed", provider=provider, error=str(e)[:200])
                    continue
            return None

        async def do_tool(name, args):
            return await self.execute_tool(ctx, name, args)

        from app.services.agent.loop import run_agent_loop
        async for ev in run_agent_loop(
            llm_call=llm_call, execute_tool=do_tool,
            messages=messages, tools=tools, max_iterations=25,
        ):
            yield f"data: {json.dumps(ev)}\n\n"

        if usage["in"] > 0:
            pricing = {"deepseek": (0.014, 0.028), "openai": (0.15, 0.60),
                       "anthropic": (0.30, 1.50), "groq": (0.0, 0.0)}
            rate_in, rate_out = pricing.get(usage["provider"], (0.014, 0.028))
            total_cost = (int(usage["in"] * rate_in / 1000 * 100)
                          + int(usage["out"] * rate_out / 1000 * 100))
            try:
                await log_cost(usage["provider"], usage["model"], "chat",
                               usage["in"], usage["out"], total_cost)
            except Exception:
                pass
            try:
                await log_audit("chat_query", "conversation", "",
                                f"Chat: {user_message[:80]}", usage["calls"],
                                usage["in"] + usage["out"], total_cost, "success")
            except Exception:
                pass

        yield "data: [DONE]\n\n"

    async def plan_task(self, task: str, repo_id: str | None = None, db=None) -> str:
        ctx = AgentContext(repo_id=repo_id, db=db)
        ctx.state = AgentState.PLANNING

        context = ""
        try:
            if ctx.db:
                context = await self.rag.build_context_for_task(ctx.db, task, repo_id)
                # Add repo list
                from app.models.repo import Repo
                from sqlalchemy import select
                result = await ctx.db.execute(select(Repo).where(Repo.is_active == True).limit(10))
                repos = result.scalars().all()
                if repos:
                    context += "\nOnboarded repos: " + ", ".join(r.local_name for r in repos)
        except Exception:
            pass

        prompt = PLANNING_PROMPT.format(task=task, context=context)
        
        # Use direct LiteLLM call that's proven to work
        from litellm import acompletion
        from app.config import settings as s
        import asyncio
        
        providers = await self.llm._get_available_providers()
        for provider, model, key in providers:
            try:
                response = await acompletion(
                    model="deepseek/deepseek-chat" if provider == "deepseek" else f"{provider}/{model}",
                    messages=[{"role": "system", "content": self._get_persona_prompt()},
                              {"role": "user", "content": prompt}],
                    api_key=key, temperature=0.2, max_tokens=2000,
                )
                return response.choices[0].message.content or ""
            except Exception:
                continue
        return "Unable to generate a plan. Please check your LLM configuration."

    async def generate_code(
        self,
        task: str,
        language: str,
        related_files: dict[str, str] | None = None,
    ) -> str:
        context = ""
        if related_files:
            for fpath, content in related_files.items():
                context += f"\n### {fpath}\n```{language}\n{content[:2000]}\n```\n"

        conventions = self.memory.get_conventions()
        prompt = CODE_GENERATION_PROMPT.format(
            task=task,
            language=language,
            context=context,
            conventions=conventions,
        )
        code = await self.llm.simple_prompt(
            system=self._get_persona_prompt(),
            user=prompt,
        )
        return code

    async def self_review(self, summary: str, files: list[str], diff: str) -> str:
        prompt = SELF_REVIEW_PROMPT.format(
            summary=summary,
            files="\n".join(f"- {f}" for f in files),
            diff=diff,
        )
        result = await self.llm.simple_prompt(
            system=self._get_persona_prompt(),
            user=prompt,
            temperature=0.1,
        )
        return result

    async def validate_code(self, code: str, file_path: str = "generated.py") -> tuple[bool, str]:
        result = guardrails.run_all_checks(code, file_path)
        if result == GuardResult.BLOCK:
            return False, "Code blocked by guardrails: contains secrets or critical security issues."
        if result == GuardResult.WARN:
            return True, "Code passed with warnings. Review the flagged items before merging."

        return True, "All checks passed."

    async def execute_tool(
        self,
        ctx: AgentContext,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}

        logger.info("tool_executing", tool=tool_name, args=str(arguments)[:200])

        try:
            result = await self._dispatch_tool(ctx, tool_name, arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error("tool_failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def _dispatch_tool(self, ctx: AgentContext, tool_name: str, args: dict) -> Any:
        if tool_name in ("semantic_search", "find_owner", "find_dependents",
                         "find_dependencies", "get_architecture", "search_notes",
                         "write_note", "read_file", "list_directory", "glob_search",
                         "run_command", "ask_question", "report_status", "graph_query",
                         "explain_architecture", "trace_issue", "list_prs"):
            return await self._dispatch_legacy(tool_name, args, ctx)
        elif tool_name == "write_file":
            return await self._tool_write_file(args, ctx)
        elif tool_name == "edit_file":
            return await self._tool_edit_file(args, ctx)
        elif tool_name == "grep_search":
            return await self._tool_grep_search(args)
        elif tool_name == "web_search":
            return await self._tool_web_search(args)
        elif tool_name == "create_branch":
            return await self._tool_create_branch(args, ctx)
        elif tool_name == "commit_files":
            return await self._tool_commit_files(args, ctx)
        elif tool_name == "create_pr":
            return await self._tool_create_pr(args, ctx)
        elif tool_name == "get_diff":
            return await self._tool_get_diff(args)
        elif tool_name == "get_blame":
            return await self._tool_get_blame(args)
        elif tool_name == "get_commit_log":
            return await self._tool_get_commit_log(args)
        elif tool_name == "run_tests":
            return {"error": "Test execution requires CI integration (not yet wired)"}
        elif tool_name == "run_lint":
            return await self._tool_run_lint(args)
        elif tool_name == "http_request":
            return await self._tool_http_request(args)
        elif tool_name == "schedule_task":
            return await self._tool_schedule_task(args, ctx)

        return await self._dispatch_legacy(tool_name, args, ctx)

    async def _tool_write_file(self, args: dict, ctx: AgentContext) -> dict:
        if not _is_safe_path(args["file_path"]):
            return {"error": "Path outside allowed directories"}
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _Path(args["file_path"]).write_text(args["content"]))
        return {"written": True, "file_path": args["file_path"]}

    async def _tool_edit_file(self, args: dict, ctx: AgentContext) -> dict:
        if not _is_safe_path(args["file_path"]):
            return {"error": "Path outside allowed directories"}
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, lambda: _Path(args["file_path"]).read_text())
        if args["old_string"] not in content:
            return {"error": "old_string not found in file"}
        new_content = content.replace(args["old_string"], args["new_string"], 1)
        await loop.run_in_executor(None, lambda: _Path(args["file_path"]).write_text(new_content))
        return {"edited": True, "file_path": args["file_path"]}

    async def _tool_web_search(self, args: dict) -> dict:
        from app.services.agent.web_search import web_search
        return await web_search(args["query"], args.get("max_results", 5))

    async def _tool_grep_search(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        base = _Path(args.get("path") or "/data/repos")
        if not _is_safe_path(str(base)):
            return {"error": "Path outside allowed directories"}
        results = await loop.run_in_executor(None, lambda: self._sync_grep(base, args["pattern"], args.get("include")))
        return {"matches": results[:50], "count": len(results)}

    def _sync_grep(self, base, pattern, include):
        import fnmatch
        results = []
        compiled = _re.compile(pattern)
        for fp in base.rglob("*"):
            if ".git" in fp.parts:
                continue
            if include and not fnmatch.fnmatch(fp.name, include):
                continue
            if fp.is_file():
                try:
                    for i, line in enumerate(fp.read_text(errors="replace").splitlines(), 1):
                        if compiled.search(line):
                            results.append({"file": str(fp), "line": i, "text": line[:200]})
                except Exception:
                    pass
        return results

    async def _tool_create_branch(self, args: dict, ctx: AgentContext) -> dict:
        loop = asyncio.get_running_loop()
        from app.utils.git import create_branch
        name = args["name"]
        base = args.get("base", "main")
        repo_path = f"/data/repos/{ctx.repo_name or 'unknown'}"
        ref = await loop.run_in_executor(
            None, lambda: create_branch(repo_path, name, base),
        )
        ctx.branch = name
        return {"branch": name, "ref": ref}

    async def _tool_commit_files(self, args: dict, ctx: AgentContext) -> dict:
        if not ctx.branch:
            return {"error": "No active branch. Create a branch first."}
        loop = asyncio.get_running_loop()
        import pygit2
        def _commit():
            repo_path = f"/data/repos/{ctx.repo_name or ''}"
            repo = pygit2.Repository(repo_path)
            for fpath, content in args["files"].items():
                abs_path = _Path(repo_path) / fpath
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content)
            repo.index.add_all()
            repo.index.write()
            tree = repo.index.write_tree()
            sig = pygit2.Signature(settings.teammate_name, f"{settings.teammate_name.lower()}@teammatex.local")
            oid = repo.create_commit(
                f"refs/heads/{ctx.branch}", sig, sig, args["message"], tree,
                [repo.head.target],
            )
            return str(oid)
        oid = await loop.run_in_executor(None, _commit)
        ctx.files_modified.extend(args["files"].keys())
        return {"commit": oid, "files": len(args["files"])}

    async def _tool_create_pr(self, args: dict, ctx: AgentContext) -> dict:
        scm = None
        try:
            from app.services.integrations.base import IntegrationRegistry
            scm = IntegrationRegistry.get_scm()
        except Exception:
            pass
        if not scm:
            return {"error": "No SCM provider configured"}
        if not ctx.branch:
            return {"error": "No active branch"}
        pr = await scm.create_pr(
            ctx.repo_name or "unknown",
            args["title"], args["body"],
            ctx.branch, args.get("base", "main"),
        )
        return {"pr_number": pr.number, "title": pr.title, "url": pr.url}

    async def _tool_create_pr_with_changes(self, args: dict, ctx: AgentContext) -> dict:
        import pygit2
        repo_name = args["repo_name"]
        branch = args["branch"]
        files = args.get("files", {})
        commit_msg = args.get("commit_message", "Update")
        repo_path = f"/data/repos/{repo_name}"
        loop = asyncio.get_running_loop()

        def _do():
            try:
                repo = pygit2.Repository(repo_path)
            except Exception:
                return {"error": f"Repo not found at {repo_path}"}

            try:
                base = repo.head.target
                repo.branches.local.create(branch, repo[base])
                repo.checkout(f"refs/heads/{branch}")
            except pygit2.errors.ExistsError:
                repo.checkout(f"refs/heads/{branch}")
            except Exception as e:
                return {"error": f"Branch failed: {e}"}

            from pathlib import Path as _P
            written = []
            for fpath, content in files.items():
                abs_path = _P(repo_path) / fpath
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content)
                written.append(fpath)

            repo.index.add_all()
            repo.index.write()
            tree = repo.index.write_tree()
            sig = pygit2.Signature("TeammateX", "teammatex@local")
            oid = repo.create_commit(
                f"refs/heads/{branch}", sig, sig, commit_msg, tree, [base]
            )

            return {
                "branch": branch, "commit": str(oid)[:8], "files": written,
                "repo": repo_name,
            }

        result = await loop.run_in_executor(None, _do)
        if "commit" in result:
            ctx.branch = result["branch"]
            ctx.files_modified = result["files"]
        return result

    async def _tool_get_diff(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        import pygit2
        def _diff():
            repo = pygit2.Repository("/data/repos")
            base_ref = args.get("base", "HEAD~1")
            head_ref = args.get("head", "HEAD")
            base = repo.revparse_single(base_ref)
            head = repo.revparse_single(head_ref)
            diff = repo.diff(base, head)
            return diff.patch or ""
        patch = await loop.run_in_executor(None, _diff)
        return {"diff": patch[:5000]}

    async def _tool_get_blame(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        import pygit2
        def _blame():
            repo = pygit2.Repository("/data/repos")
            blame = repo.blame(args["file_path"])
            results = []
            for hunk in blame:
                start = max(args.get("start_line", 1) - 1, 0)
                end = min(args.get("end_line", 999999), start + 50)
                if hunk.final_start_line_number >= start and hunk.final_start_line_number <= end:
                    results.append({
                        "line": hunk.final_start_line_number,
                        "commit": str(hunk.final_commit_id)[:8],
                        "author": hunk.final_committer.name,
                    })
            return results[:50]
        entries = await loop.run_in_executor(None, _blame)
        return {"blame": entries}

    async def _tool_get_commit_log(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        import pygit2
        def _log():
            repo = pygit2.Repository("/data/repos")
            limit = args.get("limit", 20)
            commits = []
            for commit in repo.walk(repo.head.target):
                commits.append({
                    "hash": str(commit.id)[:8],
                    "message": commit.message.strip()[:200],
                    "author": commit.author.name,
                    "time": str(commit.author.time),
                })
                if len(commits) >= limit:
                    break
            return commits
        commits = await loop.run_in_executor(None, _log)
        return {"commits": commits}

    async def _tool_run_lint(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        process = await asyncio.create_subprocess_exec(
            "ruff", "check", args["path"],
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"error": "Lint timed out"}
        return {
            "exit_code": process.returncode,
            "issues": stdout.decode(errors="replace")[:3000],
        }

    async def _tool_http_request(self, args: dict) -> dict:
        import httpx
        from urllib.parse import urlparse
        domain = urlparse(args["url"]).netloc or urlparse(args["url"]).hostname or ""
        if not domain:
            return {"error": "Invalid URL"}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(
                args["method"], args["url"],
                headers=args.get("headers"),
                content=args.get("body"),
            )
        return {
            "status": response.status_code,
            "body": response.text[:3000],
        }

    async def _tool_schedule_task(self, args: dict, ctx: AgentContext) -> dict:
        from app.workers.celery_app import celery_app
        celery_app.send_task(
            "health_check",
            eta=args["trigger_time"],
        )
        return {"scheduled": True, "name": args["name"]}

    async def _dispatch_legacy(self, tool_name: str, args: dict, ctx: AgentContext) -> Any:
        if tool_name == "semantic_search":
            if not ctx.db:
                return []
            return await self.rag.embedder.search(
                ctx.db, query=args["query"], repo_id=args.get("repo_id") or ctx.repo_id,
                entity_type=args.get("entity_type"), language=args.get("language"),
                limit=args.get("limit", 10),
            )
        elif tool_name == "find_owner":
            return await self.rag.graph.find_owner(
                args.get("repo_id") or ctx.repo_id or "", args["file_path"],
            )
        elif tool_name == "find_dependents":
            return await self.rag.graph.find_dependents(
                args.get("repo_id") or ctx.repo_id or "", args["entity_name"],
            )
        elif tool_name == "find_dependencies":
            return await self.rag.graph.find_dependencies(
                args.get("repo_id") or ctx.repo_id or "", args["entity_name"],
            )
        elif tool_name == "get_architecture":
            return await self.rag.graph.get_architecture(
                args.get("repo_id") or ctx.repo_id or "",
            )
        elif tool_name == "search_notes":
            from app.services.knowledge.notes import NotesService
            if not ctx.db:
                return []
            notes = await NotesService().search(ctx.db, args["query"], args.get("limit", 20))
            return [{"id": str(n.id), "title": n.title, "snippet": n.content[:200]} for n in notes]
        elif tool_name == "write_note":
            from app.services.knowledge.notes import NotesService
            if not ctx.db:
                return {"error": "No database session"}
            note = await NotesService().create(
                ctx.db, args["title"], args["content"],
                args.get("entity_type"), args.get("entity_id"),
            )
            return {"id": str(note.id), "title": note.title}
        elif tool_name == "read_file":
            path = _Path(args["file_path"])
            if not _is_safe_path(str(path)):
                return {"error": "Path outside allowed directories"}
            if not path.exists():
                return {"error": "File not found"}
            loop = asyncio.get_running_loop()
            lines = await loop.run_in_executor(None, lambda: path.read_text().splitlines())
            start = max(0, (args.get("start_line") or 1) - 1)
            end = min(len(lines), args.get("end_line") or len(lines))
            return {
                "content": "\n".join(lines[start:end]),
                "lines": end - start, "total_lines": len(lines),
            }
        elif tool_name == "list_directory":
            path = _Path(args["path"])
            if not _is_safe_path(str(path)):
                return {"error": "Path outside allowed directories"}
            if not path.exists():
                return {"error": "Directory not found"}
            loop = asyncio.get_running_loop()
            entries = await loop.run_in_executor(None, lambda: [
                {"name": e.name, "type": "directory" if e.is_dir() else "file",
                 "size": e.stat().st_size if e.is_file() else 0}
                for e in sorted(path.iterdir())
            ])
            return entries
        elif tool_name == "glob_search":
            base = _Path(args.get("path") or ".")
            if not _is_safe_path(str(base)):
                return {"error": "Path outside allowed directories"}
            loop = asyncio.get_running_loop()
            matches = await loop.run_in_executor(None, lambda: [str(m) for m in base.glob(args["pattern"])][:100])
            return matches
        elif tool_name == "graph_query":
            return await self.rag.graph.search_graph(
                args["query"], limit=args.get("limit", 10),
            )
        elif tool_name == "explain_architecture":
            from app.services.reporting.docs_generator import docs_generator
            result = await docs_generator.generate_repo_docs(args["repo_id"], "")
            return {"architecture": result}
        elif tool_name == "trace_issue":
            from app.services.agent.blame_tracer import blame_tracer
            result = await blame_tracer.trace(
                args["repo_id"], "", args["entity_name"],
                args.get("file_path", ""), "",
            )
            return result
        elif tool_name == "list_prs":
            from app.config import settings as _s
            token = _s.github_client_secret or _s.github_webhook_secret
            if not token:
                try:
                    from sqlalchemy import select as _sel
                    from app.models.app_config import AppConfig
                    result = await ctx.db.execute(_sel(AppConfig).where(AppConfig.key == "github_token"))
                    row = result.scalar_one_or_none()
                    if row and row.value:
                        import json as _json
                        token_data = _json.loads(row.value) if isinstance(row.value, str) else row.value
                        token = token_data.get("token", "")
                except Exception:
                    pass
            if not token:
                return {"error": "GitHub token not found. Set it in Settings."}

            from app.models.repo import Repo
            from sqlalchemy import select as _sel2
            repo_name = args.get("repo_name", "")
            state = args.get("state", "open")
            limit = args.get("limit", 10)

            # If no repo or 'all', query all active repos
            repos_to_check = []
            try:
                result = await ctx.db.execute(_sel2(Repo).where(Repo.is_active == True))
                all_repos = result.scalars().all()
                if not repo_name or repo_name == "all":
                    repos_to_check = all_repos
                else:
                    matched = [r for r in all_repos if r.local_name == repo_name]
                    repos_to_check = matched if matched else all_repos
            except Exception:
                repos_to_check = []

            from app.services.integrations.github import GitHubProvider
            provider = GitHubProvider(token=token)
            all_prs = []
            try:
                for repo in repos_to_check[:5]:
                    full_name = repo.local_name
                    if repo.github_url:
                        url = repo.github_url.rstrip("/").rstrip(".git")
                        parts = url.split("/")
                        if len(parts) >= 2:
                            full_name = f"{parts[-2]}/{parts[-1]}"
                    try:
                        prs = await provider.list_prs(full_name, state)
                        for p in prs[:3]:
                            all_prs.append({"repo": repo.local_name, "github": full_name,
                                "number": p.number, "title": p.title, "url": p.url})
                    except Exception:
                        pass
                return {"count": len(all_prs), "prs": all_prs[:limit]}
            except Exception as e:
                return {"error": f"Failed: {str(e)}"}
            finally:
                await provider.close()
        elif tool_name == "run_command":
            import subprocess
            loop = asyncio.get_running_loop()
            timeout = args.get("timeout", 120)
            def _run():
                try:
                    result = subprocess.run(
                        args["command"], shell=True, capture_output=True, text=True,
                        timeout=timeout, cwd=args.get("cwd") or "/data/repos",
                    )
                    return {
                        "exit_code": result.returncode,
                        "stdout": result.stdout[:5000],
                        "stderr": result.stderr[:2000],
                    }
                except subprocess.TimeoutExpired:
                    return {"error": f"Command timed out after {timeout}s", "exit_code": -1}
            return await loop.run_in_executor(None, _run)
        elif tool_name == "ask_question":
            logger.info("question_raised", task=args["task_id"], question=args["question"][:200])
            return {"status": "pending", "question": args["question"]}
        elif tool_name == "report_status":
            return {
                "state": ctx.state.value, "repo": ctx.repo_name,
                "branch": ctx.branch, "files_modified": len(ctx.files_modified),
                "memory_items": len(self.memory.working),
            }
        return {"error": f"Tool {tool_name} not implemented"}


agent_runtime = AgentRuntime()
