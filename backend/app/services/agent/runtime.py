import asyncio
import contextlib
import json
import os
import re as _re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path as _Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.config import settings
from app.services.agent.cost_tracker import log_audit, log_cost, record_llm_usage
from app.services.agent.guardrails import GuardResult, guardrails
from app.services.agent.memory import MemoryManager
from app.services.agent.prompts import (
    CODE_GENERATION_PROMPT,
    DEFAULT_PERSONA,
    PERSONA_PROMPTS,
    PERSONA_STYLES,
    PLANNING_PROMPT,
    SELF_REVIEW_PROMPT,
    persona_directive,
)
from app.services.agent.rag import RAGPipeline
from app.services.agent.tools import tool_registry
from app.services.llm.provider import LLMProvider


def _with_prompt_cache(messages: list[dict]) -> list[dict]:
    """Mark the (static) system prompt as an Anthropic cache breakpoint.

    The system prompt + tool schemas are re-sent on every turn of the agent
    loop; on Anthropic that prefix is reprocessed (and re-billed) each time
    unless an explicit ``cache_control`` breakpoint is set. DeepSeek and OpenAI
    cache matching prefixes automatically, so this is only needed — and only
    applied — for Anthropic. Returns a shallow copy; never mutates the caller's
    list (the loop keeps appending to the original)."""
    if not messages or messages[0].get("role") != "system":
        return messages
    content = messages[0].get("content")
    if not isinstance(content, str):
        return messages  # already block-formatted; leave it alone
    cached_system = {
        "role": "system",
        "content": [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}},
        ],
    }
    return [cached_system, *messages[1:]]


def _get_github_token() -> str:
    from app.config import settings as _s

    token = _s.github_client_secret or _s.github_webhook_secret
    if not token:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(_s.database_url.replace("+asyncpg", "+psycopg2"))
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value FROM app_config WHERE key = 'github_token'")
                ).fetchone()
                if row and row[0]:
                    import json as _json

                    data = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    token = data.get("token", "")
            engine.dispose()
        except Exception:
            pass
    return token


logger = get_logger(__name__)

# The agent only ever has legitimate business inside the cloned repos and the
# uploads/scratch volumes. Confining file tools here stops a path like
# /proc/<pid>/environ (process secrets), /etc/shadow, or the app source from
# being read/written through read_file/write_file/edit_file/list/glob/grep.
_WORKSPACE_ROOTS = ("/data/repos", "/data/uploads", "/tmp")


def _safe_realpath(path: str) -> str | None:
    """Return the canonicalized real path if it resolves inside an allowed
    workspace root, else None. Symlinks and ``..`` are resolved first so nothing
    inside the workspace can escape it. Callers must use the *returned* value for
    filesystem access, so the path that was validated is the one that gets used."""
    if not path or not str(path).strip():
        return None
    try:
        real = os.path.realpath(str(path))
    except (OSError, ValueError):
        return None
    if any(real == r or real.startswith(r + os.sep) for r in _WORKSPACE_ROOTS):
        return real
    return None


def _is_safe_path(path: str) -> bool:
    """True only if `path` resolves inside an allowed workspace root."""
    return _safe_realpath(path) is not None


def _resolve_repo_path(ctx: "AgentContext | None", args: dict) -> str | None:
    """Resolve which clone under /data/repos a git tool should operate on.

    The git tools used to open ``pygit2.Repository("/data/repos")`` — but that's
    the *parent* of the clones, not a repo, so every call raised. Resolve a real
    repo: an explicit ``repo_name`` arg, else the active context repo, else the
    sole clone if there's exactly one. Returns a validated path or None."""
    root = "/data/repos"
    name = (args.get("repo_name") or (getattr(ctx, "repo_name", None) or "")).strip().strip("/")
    if not name:
        try:
            dirs = [p for p in os.listdir(root) if os.path.isdir(os.path.join(root, p, ".git"))]
        except OSError:
            dirs = []
        if len(dirs) == 1:
            name = dirs[0]
        else:
            return None
    real = _safe_realpath(os.path.join(root, name))
    if real is None:
        return None
    return real if os.path.isdir(os.path.join(real, ".git")) else None


# Environment-variable names that carry secrets and must never be exposed to a
# shell/process the agent runs (run_command / run_lint). Matched as a substring,
# case-insensitive, so OPENAI_API_KEY, TEAMMATEX_SECRET_KEY, POSTGRES_PASSWORD,
# JIRA_API_TOKEN, etc. are all stripped while PATH/HOME/LANG survive.
_SECRET_ENV_RE = _re.compile(
    r"SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|_KEY$|PRIVATE|CREDENTIAL", _re.IGNORECASE
)


def _scrubbed_env() -> dict:
    """A copy of the process environment with secret-bearing vars removed, for
    handing to agent-invoked subprocesses so `env`/`printenv`/`echo $VAR` can't
    leak the JWT signing key or integration credentials."""
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}


def _url_ssrf_safe(url: str) -> tuple[bool, str, str | None]:
    """Reject URLs that would let http_request reach the host's own internals.

    The model picks the URL, so a prompt-injected or confused agent could aim it
    at the cloud metadata endpoint (169.254.169.254), localhost services, or an
    internal-network address to exfiltrate credentials/SSRF. We allow only
    http(s), then resolve the host and refuse if *any* resolved address is
    private, loopback, link-local, or otherwise reserved.

    Returns (ok, reason, pinned_ip). ``pinned_ip`` is one validated address the
    caller should connect to directly, closing the DNS-rebind window between this
    check and the real request; it is None whenever ok is False."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme '{parsed.scheme}' not allowed (use http/https)", None
    host = parsed.hostname
    if not host:
        return False, "missing host", None
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as e:
        return False, f"could not resolve host: {e}", None
    pinned_ip = None
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            return False, f"unparseable address {addr}", None
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False, f"host resolves to non-public address {ip}", None
        if pinned_ip is None:
            pinned_ip = str(ip)
    return True, "", pinned_ip


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


# Which permission capability gates each tool. Tools absent from this map are
# ungated. read_code / write_code / create_pr line up with the Settings toggles;
# merge_pr and autonomous have no tools yet (no merge tool; autonomy is a mode).
TOOL_CAPABILITY: dict[str, str] = {
    "read_file": "read_code",
    "list_directory": "read_code",
    "glob_search": "read_code",
    "grep_search": "read_code",
    "get_diff": "read_code",
    "get_blame": "read_code",
    "get_commit_log": "read_code",
    "semantic_search": "read_code",
    "graph_query": "read_code",
    "find_owner": "read_code",
    "find_dependents": "read_code",
    "find_dependencies": "read_code",
    "get_architecture": "read_code",
    "search_notes": "read_code",
    "list_prs": "read_code",
    "trace_issue": "read_code",
    "write_file": "write_code",
    "edit_file": "write_code",
    "commit_files": "write_code",
    "create_branch": "write_code",
    "create_pr": "create_pr",
    "run_command": "execute",
    "run_lint": "execute",
    "run_tests": "execute",
}


class AgentRuntime:
    def __init__(self):
        self.memory = MemoryManager()
        self.rag = RAGPipeline()
        self.tools = tool_registry
        self.llm = LLMProvider()

    async def _resolve_persona(self, db: AsyncSession | None) -> str:
        """The active persona key: app_config['persona'] if set, else
        settings.teammate_persona, normalized to a known persona."""
        persona = settings.teammate_persona
        if db is not None:
            from sqlalchemy import select as _sel

            from app.models.app_config import AppConfig

            try:
                row = (
                    await db.execute(_sel(AppConfig).where(AppConfig.key == "persona"))
                ).scalar_one_or_none()
                if row and isinstance(row.value, dict) and row.value.get("persona"):
                    persona = row.value["persona"]
            except Exception:
                pass
        return persona if persona in PERSONA_STYLES else DEFAULT_PERSONA

    def _get_persona_prompt(self, persona: str | None = None) -> str:
        base = PERSONA_PROMPTS["helpful_senior_dev"].format(name=settings.teammate_name)
        return f"{base}\n{persona_directive(persona)}"

    # Tools the chat agent is allowed to drive. A small, powerful set: a real
    # shell does the git/gh/test work, so there are no scripted git tools. The
    # knowledge tools (semantic_search/graph_query/get_architecture) are included
    # now that the embeddings + graph pipelines actually return data — they let
    # the agent jump straight to relevant code instead of brute-force grepping.
    CORE_TOOLS = {
        "read_file",
        "write_file",
        "edit_file",
        "list_directory",
        "glob_search",
        "grep_search",
        "run_command",
        "web_search",
        "semantic_search",
        "graph_query",
        "get_architecture",
        "find_dependents",
        "find_dependencies",
        "find_owner",
        # Persistent team memory (remember/recall decisions) + issue tracing
        # via the call graph — capabilities a plain RAG bot doesn't have.
        "write_note",
        "search_notes",
        "trace_issue",
    }

    def _curated_tools(self) -> list[dict]:
        return [
            t for t in self.tools.get_openai_tools() if t["function"]["name"] in self.CORE_TOOLS
        ]

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

    def _build_system_prompt(
        self, context: str, env_block: str, github_connected: bool, persona: str = DEFAULT_PERSONA
    ) -> str:
        name = settings.teammate_name
        git_caps = (
            "git is installed and configured, and the `gh` GitHub CLI is installed "
            "and authenticated — so you can branch, edit, commit, push, and open "
            "real pull requests entirely on your own by running commands."
            if github_connected
            else "git is installed for local work; pushing or opening a PR needs a GitHub "
            "token, so if the user asks for a PR and one isn't configured, tell them "
            "to add a token in Settings."
        )
        parts = [
            f"You are {name}, an autonomous software-engineering teammate working on "
            f"the user's codebases. You are NOT Claude, GPT, or any specific model.",
            "",
            persona_directive(persona),
            "",
            "You have a real Linux shell with full access via the run_command tool, "
            "plus tools to read/write/edit files, search code (grep/glob), and search "
            f"the live web. {git_caps}",
            "",
            "You also have capabilities a plain chatbot doesn't: a semantic + graph "
            "index of the onboarded code (semantic_search, graph_query, get_architecture, "
            "find_dependents/find_dependencies to answer 'who calls this / what does this "
            "depend on', find_owner for 'who owns this file / who should review it', and "
            "trace_issue to find code related to a break), plus a "
            "persistent team memory (write_note to record a decision or convention, "
            "search_notes to recall one later). Use write_note whenever the user states a "
            "lasting decision, preference, or convention so you remember it next time. "
            "When asked, you can also produce module/architecture docs, a standup, or "
            "release notes by combining these tools with git history — just do it.",
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
        self,
        db: AsyncSession,
        user_message: str,
        repo_id: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        import json

        from litellm import acompletion

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
        persona = await self._resolve_persona(db)
        system_prompt = self._build_system_prompt(context, env_block, github_connected, persona)

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            for msg in conversation_history[-30:]:
                if msg.get("role") in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        tools = self._curated_tools()

        usage = {
            "in": 0,
            "out": 0,
            "calls": 0,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
        }

        async def llm_call(msgs, tls):
            providers = await LLMProvider._get_available_providers()
            for provider, model, key in providers:
                try:
                    actual_model = LLMProvider._get_model_name(provider, model)
                    send_msgs = _with_prompt_cache(msgs) if provider == "anthropic" else msgs
                    resp = await acompletion(
                        model=actual_model,
                        messages=send_msgs,
                        api_key=key,
                        temperature=0.2,
                        max_tokens=2000,
                        tools=tls,
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
            llm_call=llm_call,
            execute_tool=do_tool,
            messages=messages,
            tools=tools,
            max_iterations=25,
        ):
            yield f"data: {json.dumps(ev)}\n\n"

        if usage["in"] > 0:
            from app.services.agent.cost import cost_cents

            total_cost = cost_cents(usage["model"], usage["in"], usage["out"], usage["provider"])
            with contextlib.suppress(Exception):
                await log_cost(
                    usage["provider"], usage["model"], "chat", usage["in"], usage["out"], total_cost
                )
            with contextlib.suppress(Exception):
                await log_audit(
                    "chat_query",
                    "conversation",
                    "",
                    f"Chat: {user_message[:80]}",
                    usage["calls"],
                    usage["in"] + usage["out"],
                    total_cost,
                    "success",
                )

        yield "data: [DONE]\n\n"

    async def plan_task(self, task: str, repo_id: str | None = None, db=None) -> str:
        ctx = AgentContext(repo_id=repo_id, db=db)
        ctx.state = AgentState.PLANNING

        context = ""
        try:
            if ctx.db:
                context = await self.rag.build_context_for_task(ctx.db, task, repo_id)
                # Add repo list
                from sqlalchemy import select

                from app.models.repo import Repo

                result = await ctx.db.execute(select(Repo).where(Repo.is_active == True).limit(10))
                repos = result.scalars().all()
                if repos:
                    context += "\nOnboarded repos: " + ", ".join(r.local_name for r in repos)
        except Exception:
            pass

        prompt = PLANNING_PROMPT.format(task=task, context=context)
        persona = await self._resolve_persona(ctx.db)

        # Use direct LiteLLM call that's proven to work

        from litellm import acompletion

        providers = await self.llm._get_available_providers()
        for provider, model, key in providers:
            try:
                # Use the same provider→litellm model mapping as the chat path.
                # The old hardcode ("deepseek/deepseek-chat") ignored the
                # configured model and pinned a model that DeepSeek retired on
                # 2026-07-24 — so planning 500'd on the default provider.
                response = await acompletion(
                    model=LLMProvider._get_model_name(provider, model),
                    messages=[
                        {"role": "system", "content": self._get_persona_prompt(persona)},
                        {"role": "user", "content": prompt},
                    ],
                    api_key=key,
                    temperature=0.2,
                    max_tokens=2000,
                )
                await record_llm_usage(provider, model, "plan", response)
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
            return (
                False,
                "Code blocked by guardrails: contains secrets or critical security issues.",
            )
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

        denied = await self._capability_denied(ctx, tool_name)
        if denied:
            logger.info("tool_denied", tool=tool_name, capability=denied)
            return {
                "error": f"Permission denied: the '{denied}' capability is disabled in Settings."
            }

        logger.info("tool_executing", tool=tool_name, args=str(arguments)[:200])

        try:
            result = await self._dispatch_tool(ctx, tool_name, arguments)
            return {"success": True, "data": result}
        except Exception as e:
            # The detail is logged server-side; return a generic message so an
            # unexpected exception's text (paths, DB errors, stack detail) isn't
            # streamed back through the chat SSE response to the caller.
            logger.error("tool_failed", tool=tool_name, error=str(e))
            return {"error": f"Tool '{tool_name}' failed unexpectedly."}

    async def _capability_denied(self, ctx: AgentContext, tool_name: str) -> str | None:
        """Return the gating capability if the tool is blocked, else None. Fails
        open: an unmapped tool, no DB session, or a capability with no stored row
        (the model defaults enabled) is allowed."""
        capability = TOOL_CAPABILITY.get(tool_name)
        if not capability or ctx.db is None:
            return None
        from sqlalchemy import select as _sel

        from app.models.permission import Permission

        row = (
            await ctx.db.execute(_sel(Permission).where(Permission.capability == capability))
        ).scalar_one_or_none()
        return capability if (row is not None and not row.enabled) else None

    async def _dispatch_tool(self, ctx: AgentContext, tool_name: str, args: dict) -> Any:
        if tool_name in (
            "semantic_search",
            "find_owner",
            "find_dependents",
            "find_dependencies",
            "get_architecture",
            "search_notes",
            "write_note",
            "read_file",
            "list_directory",
            "glob_search",
            "run_command",
            "graph_query",
            "trace_issue",
            "list_prs",
        ):
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
            return await self._tool_get_diff(args, ctx)
        elif tool_name == "get_blame":
            return await self._tool_get_blame(args, ctx)
        elif tool_name == "get_commit_log":
            return await self._tool_get_commit_log(args, ctx)
        elif tool_name == "run_tests":
            return {"error": "Test execution requires CI integration (not yet wired)"}
        elif tool_name == "run_lint":
            return await self._tool_run_lint(args)
        elif tool_name == "http_request":
            return await self._tool_http_request(args, ctx)
        elif tool_name == "schedule_task":
            return await self._tool_schedule_task(args, ctx)

        return await self._dispatch_legacy(tool_name, args, ctx)

    async def _tool_write_file(self, args: dict, ctx: AgentContext) -> dict:
        safe = _safe_realpath(args["file_path"])
        if safe is None:
            return {"error": "Path outside allowed directories"}
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _Path(safe).write_text(args["content"]))
        return {"written": True, "file_path": safe}

    async def _tool_edit_file(self, args: dict, ctx: AgentContext) -> dict:
        safe = _safe_realpath(args["file_path"])
        if safe is None:
            return {"error": "Path outside allowed directories"}
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, lambda: _Path(safe).read_text())
        if args["old_string"] not in content:
            return {"error": "old_string not found in file"}
        new_content = content.replace(args["old_string"], args["new_string"], 1)
        await loop.run_in_executor(None, lambda: _Path(safe).write_text(new_content))
        return {"edited": True, "file_path": safe}

    async def _tool_web_search(self, args: dict) -> dict:
        from app.services.agent.web_search import web_search

        return await web_search(args["query"], args.get("max_results", 5))

    async def _tool_grep_search(self, args: dict) -> dict:
        loop = asyncio.get_running_loop()
        safe = _safe_realpath(args.get("path") or "/data/repos")
        if safe is None:
            return {"error": "Path outside allowed directories"}
        base = _Path(safe)
        results = await loop.run_in_executor(
            None, lambda: self._sync_grep(base, args["pattern"], args.get("include"))
        )
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
            None,
            lambda: create_branch(repo_path, name, base),
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
            sig = pygit2.Signature(
                settings.teammate_name, f"{settings.teammate_name.lower()}@teammatex.local"
            )
            oid = repo.create_commit(
                f"refs/heads/{ctx.branch}",
                sig,
                sig,
                args["message"],
                tree,
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
            args["title"],
            args["body"],
            ctx.branch,
            args.get("base", "main"),
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
            oid = repo.create_commit(f"refs/heads/{branch}", sig, sig, commit_msg, tree, [base])

            return {
                "branch": branch,
                "commit": str(oid)[:8],
                "files": written,
                "repo": repo_name,
            }

        result = await loop.run_in_executor(None, _do)
        if "commit" in result:
            ctx.branch = result["branch"]
            ctx.files_modified = result["files"]
        return result

    async def _tool_get_diff(self, args: dict, ctx: AgentContext) -> dict:
        repo_path = _resolve_repo_path(ctx, args)
        if not repo_path:
            return {"error": "Repo not found — pass repo_name (the clone under /data/repos)."}
        loop = asyncio.get_running_loop()
        import pygit2

        def _diff():
            repo = pygit2.Repository(repo_path)
            base_ref = args.get("base", "HEAD~1")
            head_ref = args.get("head", "HEAD")
            base = repo.revparse_single(base_ref)
            head = repo.revparse_single(head_ref)
            diff = repo.diff(base, head)
            return diff.patch or ""

        patch = await loop.run_in_executor(None, _diff)
        return {"diff": patch[:5000]}

    async def _tool_get_blame(self, args: dict, ctx: AgentContext) -> dict:
        repo_path = _resolve_repo_path(ctx, args)
        if not repo_path:
            return {"error": "Repo not found — pass repo_name (the clone under /data/repos)."}
        loop = asyncio.get_running_loop()
        import pygit2

        def _blame():
            repo = pygit2.Repository(repo_path)
            blame = repo.blame(args["file_path"])
            results = []
            for hunk in blame:
                start = max(args.get("start_line", 1) - 1, 0)
                end = min(args.get("end_line", 999999), start + 50)
                if hunk.final_start_line_number >= start and hunk.final_start_line_number <= end:
                    results.append(
                        {
                            "line": hunk.final_start_line_number,
                            "commit": str(hunk.final_commit_id)[:8],
                            "author": hunk.final_committer.name,
                        }
                    )
            return results[:50]

        entries = await loop.run_in_executor(None, _blame)
        return {"blame": entries}

    async def _tool_get_commit_log(self, args: dict, ctx: AgentContext) -> dict:
        repo_path = _resolve_repo_path(ctx, args)
        if not repo_path:
            return {"error": "Repo not found — pass repo_name (the clone under /data/repos)."}
        loop = asyncio.get_running_loop()
        import pygit2

        def _log():
            repo = pygit2.Repository(repo_path)
            limit = args.get("limit", 20)
            commits = []
            for commit in repo.walk(repo.head.target):
                commits.append(
                    {
                        "hash": str(commit.id)[:8],
                        "message": commit.message.strip()[:200],
                        "author": commit.author.name,
                        "time": str(commit.author.time),
                    }
                )
                if len(commits) >= limit:
                    break
            return commits

        commits = await loop.run_in_executor(None, _log)
        return {"commits": commits}

    async def _tool_run_lint(self, args: dict) -> dict:
        # Confine to the workspace like the other file tools: without this the
        # agent could point ruff at arbitrary paths (e.g. read errors leaking
        # snippets of files outside /data). "--" stops a crafted path from being
        # parsed as a ruff option.
        safe = _safe_realpath((args.get("path") or "").strip())
        if safe is None:
            return {"error": "Path outside allowed directories"}
        asyncio.get_running_loop()
        process = await asyncio.create_subprocess_exec(
            "ruff",
            "check",
            "--",
            safe,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_scrubbed_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except TimeoutError:
            process.kill()
            await process.wait()
            return {"error": "Lint timed out"}
        return {
            "exit_code": process.returncode,
            "issues": stdout.decode(errors="replace")[:3000],
        }

    async def _registry_allows(self, ctx: AgentContext, url: str, method: str) -> tuple[bool, str]:
        """Enforce the approved-API allow-list the http_request description promises.

        Opt-in: with an empty registry we don't block (the SSRF guard still
        applies), so existing instances aren't bricked. Once an operator adds any
        active entry, http_request is restricted to registered domains/methods/
        paths — giving real outbound egress control without extra config."""
        if ctx is None or ctx.db is None:
            return True, ""
        try:
            from sqlalchemy import select as _sel

            from app.models.api_registry import APIRegistryEntry

            rows = (
                (
                    await ctx.db.execute(
                        _sel(APIRegistryEntry).where(APIRegistryEntry.status == "active")
                    )
                )
                .scalars()
                .all()
            )
        except Exception:
            return True, ""  # registry unavailable — fall back to SSRF guard only
        if not rows:
            return True, ""
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        entry = next((r for r in rows if r.domain == host), None)
        if not entry:
            return False, f"domain '{host}' is not in the approved API registry"
        methods = [m.upper() for m in (entry.allowed_methods or [])]
        if methods and method.upper() not in methods:
            return False, f"method {method.upper()} not allowed for {host} (allowed: {methods})"
        paths = entry.allowed_paths or []
        if paths:
            from fnmatch import fnmatch

            req_path = urlparse(url).path or "/"
            if not any(fnmatch(req_path, p) for p in paths):
                return False, f"path {req_path} not allowed for {host}"
        return True, ""

    async def _tool_http_request(self, args: dict, ctx: AgentContext) -> dict:
        import ipaddress
        from urllib.parse import urlparse, urlunparse

        import httpx

        url = args["url"]
        # SSRF guard: the model chooses this URL, so block anything that resolves
        # to the host's own internals (metadata service, localhost, LAN) before
        # we ever open the connection. DNS is resolved off the event loop.
        loop = asyncio.get_running_loop()
        ok, reason, pinned_ip = await loop.run_in_executor(None, lambda: _url_ssrf_safe(url))
        if not ok:
            logger.warning("http_request_blocked", url=url[:200], reason=reason)
            return {"error": f"URL blocked: {reason}"}
        allowed, why = await self._registry_allows(ctx, url, args["method"])
        if not allowed:
            logger.warning("http_request_registry_denied", url=url[:200], reason=why)
            return {"error": f"URL blocked: {why}"}

        # Pin the connection to the IP we just validated. httpx (via httpcore)
        # re-resolves the hostname when it connects, so a DNS answer that flips
        # from a public IP (seen by the check above) to an internal one between
        # the two lookups would sail straight past the guard — a classic
        # DNS-rebind SSRF. We swap the host for the validated IP but keep the
        # original Host header and TLS SNI so virtual hosting and certificate
        # verification still work.
        parsed = urlparse(url)
        req_url = url
        headers = dict(args.get("headers") or {})
        extensions: dict = {}
        host = parsed.hostname
        if pinned_ip and host and host != pinned_ip:
            default_port = 443 if parsed.scheme == "https" else 80
            port = parsed.port
            ip_literal = (
                f"[{pinned_ip}]" if ipaddress.ip_address(pinned_ip).version == 6 else pinned_ip
            )
            netloc = ip_literal if port is None else f"{ip_literal}:{port}"
            req_url = urlunparse(parsed._replace(netloc=netloc))
            headers.setdefault(
                "Host", host if port in (None, default_port) else f"{host}:{port}"
            )
            if parsed.scheme == "https":
                extensions["sni_hostname"] = host

        # Stream with a hard byte cap instead of buffering the whole body: an
        # approved-but-compromised endpoint could otherwise stream gigabytes and
        # OOM the API process before we ever slice to 3 KB. redirects stay off so
        # a 3xx can't bounce the request past the SSRF check to an internal host.
        _MAX_BODY = 1024 * 1024  # 1 MB read ceiling; response is truncated below
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            async with client.stream(
                args["method"],
                req_url,
                headers=headers,
                content=args.get("body"),
                extensions=extensions,
            ) as response:
                buf = bytearray()
                async for chunk in response.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) >= _MAX_BODY:
                        break
                status = response.status_code
        return {
            "status": status,
            "body": bytes(buf).decode(errors="replace")[:3000],
        }

    # Only these registered Celery tasks may be scheduled. The old code fired
    # "health_check" for *every* request and ignored the action — reporting a
    # success that did nothing. Scheduling arbitrary actions isn't supported, so
    # we accept the real tasks and reject anything else honestly.
    _SCHEDULABLE_TASKS = {"health_check", "git_pull_repos", "send_weekly_digest"}

    async def _tool_schedule_task(self, args: dict, ctx: AgentContext) -> dict:
        from datetime import datetime

        from app.workers.celery_app import celery_app

        action = args.get("action") or {}
        task_name = action.get("task") if isinstance(action, dict) else None
        if task_name not in self._SCHEDULABLE_TASKS:
            return {
                "error": f"Only these tasks can be scheduled: "
                f"{sorted(self._SCHEDULABLE_TASKS)}. Got task={task_name!r}."
            }

        trigger = (args.get("trigger_time") or "").strip()
        eta = None
        if trigger:
            try:
                eta = datetime.fromisoformat(trigger.replace("Z", "+00:00"))
            except ValueError:
                return {
                    "error": f"trigger_time must be an ISO-8601 datetime "
                    f"(cron expressions aren't supported); got {trigger!r}."
                }

        try:
            result = celery_app.send_task(
                task_name,
                eta=eta,
                kwargs=action.get("kwargs") or {},
            )
        except Exception as e:
            return {"error": f"Failed to enqueue task: {str(e)[:200]}"}
        return {
            "scheduled": True,
            "name": args["name"],
            "task": task_name,
            "id": str(result.id),
            "eta": trigger or "now",
        }

    async def _dispatch_legacy(self, tool_name: str, args: dict, ctx: AgentContext) -> Any:
        if tool_name == "semantic_search":
            if not ctx.db:
                return []
            return await self.rag.embedder.search(
                ctx.db,
                query=args["query"],
                repo_id=args.get("repo_id") or ctx.repo_id,
                entity_type=args.get("entity_type"),
                language=args.get("language"),
                limit=args.get("limit", 10),
            )
        elif tool_name == "find_owner":
            return await self.rag.graph.find_owner(
                args.get("repo_id") or ctx.repo_id or "",
                args["file_path"],
            )
        elif tool_name == "find_dependents":
            return await self.rag.graph.find_dependents(
                args.get("repo_id") or ctx.repo_id or "",
                args["entity_name"],
            )
        elif tool_name == "find_dependencies":
            return await self.rag.graph.find_dependencies(
                args.get("repo_id") or ctx.repo_id or "",
                args["entity_name"],
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
                ctx.db,
                args["title"],
                args["content"],
                args.get("entity_type"),
                args.get("entity_id"),
            )
            return {"id": str(note.id), "title": note.title}
        elif tool_name == "read_file":
            safe = _safe_realpath(args["file_path"])
            if safe is None:
                return {"error": "Path outside allowed directories"}
            path = _Path(safe)
            if not path.exists():
                return {"error": "File not found"}
            loop = asyncio.get_running_loop()
            lines = await loop.run_in_executor(None, lambda: path.read_text().splitlines())
            start = max(0, (args.get("start_line") or 1) - 1)
            end = min(len(lines), args.get("end_line") or len(lines))
            return {
                "content": "\n".join(lines[start:end]),
                "lines": end - start,
                "total_lines": len(lines),
            }
        elif tool_name == "list_directory":
            safe = _safe_realpath(args["path"])
            if safe is None:
                return {"error": "Path outside allowed directories"}
            path = _Path(safe)
            if not path.exists():
                return {"error": "Directory not found"}
            loop = asyncio.get_running_loop()
            entries = await loop.run_in_executor(
                None,
                lambda: [
                    {
                        "name": e.name,
                        "type": "directory" if e.is_dir() else "file",
                        "size": e.stat().st_size if e.is_file() else 0,
                    }
                    for e in sorted(path.iterdir())
                ],
            )
            return entries
        elif tool_name == "glob_search":
            safe = _safe_realpath(args.get("path") or "/data/repos")
            if safe is None:
                return {"error": "Path outside allowed directories"}
            base = _Path(safe)
            loop = asyncio.get_running_loop()
            matches = await loop.run_in_executor(
                None, lambda: [str(m) for m in base.glob(args["pattern"])][:100]
            )
            return matches
        elif tool_name == "graph_query":
            return await self.rag.graph.search_graph(
                args["query"],
                limit=args.get("limit", 10),
            )
        elif tool_name == "trace_issue":
            from app.services.agent.blame_tracer import blame_tracer

            result = await blame_tracer.trace(
                args["repo_id"],
                "",
                args["entity_name"],
                args.get("file_path", ""),
                "",
            )
            return result
        elif tool_name == "list_prs":
            from app.config import settings as _s

            token = _s.github_client_secret or _s.github_webhook_secret
            if not token:
                try:
                    from sqlalchemy import select as _sel

                    from app.models.app_config import AppConfig

                    result = await ctx.db.execute(
                        _sel(AppConfig).where(AppConfig.key == "github_token")
                    )
                    row = result.scalar_one_or_none()
                    if row and row.value:
                        import json as _json

                        token_data = (
                            _json.loads(row.value) if isinstance(row.value, str) else row.value
                        )
                        token = token_data.get("token", "")
                except Exception:
                    pass
            if not token:
                return {"error": "GitHub token not found. Set it in Settings."}

            from sqlalchemy import select as _sel2

            from app.models.repo import Repo

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
                            all_prs.append(
                                {
                                    "repo": repo.local_name,
                                    "github": full_name,
                                    "number": p.number,
                                    "title": p.title,
                                    "url": p.url,
                                }
                            )
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
                        args["command"],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=args.get("cwd") or "/data/repos",
                        env=_scrubbed_env(),
                    )
                    return {
                        "exit_code": result.returncode,
                        "stdout": result.stdout[:5000],
                        "stderr": result.stderr[:2000],
                    }
                except subprocess.TimeoutExpired:
                    return {"error": f"Command timed out after {timeout}s", "exit_code": -1}

            return await loop.run_in_executor(None, _run)
        return {"error": f"Tool {tool_name} not implemented"}


agent_runtime = AgentRuntime()
