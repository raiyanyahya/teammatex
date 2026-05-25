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

logger = get_logger(__name__)

SAFE_ROOTS = ["/data/repos", "/tmp", "/app"]


def _is_safe_path(path: str) -> bool:
    resolved = _Path(path).resolve()
    return any(
        str(resolved).startswith(_Path(r).resolve().as_posix())
        for r in SAFE_ROOTS
    )


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

    async def chat(
        self, db: AsyncSession, user_message: str,
        repo_id: str | None = None, conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        from litellm import acompletion
        import json

        ctx = AgentContext(repo_id=repo_id, db=db)

        try:
            context = await self.rag.retrieve_context(db, user_message, repo_id)
        except Exception:
            context = ""

        repo_details = []
        github_connected = False
        try:
            from app.models.repo import Repo
            from sqlalchemy import select
            result = await db.execute(select(Repo).where(Repo.is_active == True).limit(10))
            repos = result.scalars().all()
            for r in repos:
                detail = f"- **{r.local_name}**: {r.default_branch or 'main'}"
                if hasattr(r, 'language') and r.language:
                    detail += f", primary: {r.language}"
                repo_details.append(detail)
            if repos:
                context += f"\n\nOnboarded repos ({len(repos)}):\n" + "\n".join(repo_details)
            # Check GitHub integration (env or DB)
            from app.config import settings as _s
            github_connected = bool(_s.github_client_secret or _s.github_webhook_secret)
            if not github_connected:
                try:
                    from sqlalchemy import select as _sel
                    from app.models.app_config import AppConfig
                    result = await db.execute(_sel(AppConfig).where(AppConfig.key == "github_token"))
                    row = result.scalar_one_or_none()
                    if row and row.value:
                        import json as _json
                        token_data = _json.loads(row.value) if isinstance(row.value, str) else row.value
                        if token_data.get("token"):
                            github_connected = True
                except Exception:
                    pass
        except Exception:
            pass

        # Build capabilities list
        capabilities = [
            "File reading and directory listing",
            "Code search via regex and semantic search",
            "Knowledge graph queries (entities, dependencies, architecture)",
            "Git commit log, diff, and blame",
        ]
        if github_connected:
            capabilities.append("GitHub API: PR listing, branch creation, code review posting")

        system_prompt = self._get_persona_prompt()
        system_prompt += f"\n\nCodebase knowledge:\n{context}"

        system_prompt += f"""
\n\nYOUR CAPABILITIES: {', '.join(capabilities)}.

RULES FOR USING TOOLS:
- For simple factual questions about the codebase (repos, languages, file counts, overview),
  answer DIRECTLY from the knowledge above. DO NOT use tools.
- For git operations (branches, commits, logs), use run_command with the repo path.
  Example: cd /data/repos/kit-fork && git log --oneline -5
- Only use graph_query/semantic_search when you genuinely need codebase search.
- NEVER say \"I don't have access\" or \"not cloned\" — repos ARE cloned at /data/repos/.
- If a tool returns empty or error, stop after 2 attempts and tell the user what you found.
- Be a real teammate: direct, helpful, and conversational. No corporate speak."""

        if not github_connected:
            system_prompt += "\n\n(GitHub not connected. For local git: use run_command. For PRs: suggest Settings.)"
        else:
            system_prompt += "\n\n(GitHub connected: use list_prs for pull requests.)"

        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            for msg in conversation_history[-30:]:
                if msg.get("role") in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        tools = self.tools.get_openai_tools()
        max_iterations = 5
        empty_tool_results = 0
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost = 0
        llm_call_count = 0
        used_provider = "deepseek"
        used_model_name = "deepseek-chat"

        for iteration in range(max_iterations):
            providers = await LLMProvider._get_available_providers()
            response = None

            for provider, model, key in providers:
                try:
                    actual_model = "deepseek/deepseek-chat" if provider == "deepseek" else f"{provider}/{model}"
                    response = await acompletion(
                        model=actual_model, messages=messages, api_key=key,
                        temperature=0.2, max_tokens=2000, tools=tools,
                    )
                    used_provider = provider
                    used_model_name = model
                    break
                except Exception:
                    continue

            if not response:
                yield "data: {\"type\":\"error\",\"content\":\"LLM unavailable\"}\n\n"
                return

            choice = response.choices[0]
            msg = choice.message
            llm_call_count += 1
            if response.usage:
                total_tokens_in += response.usage.prompt_tokens or 0
                total_tokens_out += response.usage.completion_tokens or 0

            has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls

            if msg.content and not has_tool_calls:
                yield f"data: {json.dumps({'type': 'text', 'content': msg.content})}\n\n"
                messages.append({"role": "assistant", "content": msg.content})
                break

            if not has_tool_calls:
                break

            for tc in msg.tool_calls[:5]:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments

                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'args': str(tool_args)[:200]})}\n\n"

                try:
                    result = await self.execute_tool(ctx, tool_name, tool_args)
                    result_str = json.dumps(result)[:3000]
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})

                # Track empty/useless results
                parsed = json.loads(result_str) if isinstance(result_str, str) else result_str
                if isinstance(parsed, dict):
                    data = parsed.get("data", parsed)
                    if data == [] or data == {} or data == 0 or data == "" or data is None:
                        empty_tool_results += 1
                    elif isinstance(data, dict) and data.get("error"):
                        empty_tool_results += 1
                    else:
                        empty_tool_results = 0

                yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name, 'result': result_str[:500]})}\n\n"

                messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

            if empty_tool_results >= 3:
                yield "data: {\"type\":\"text\",\"content\":\"(Looking into this, but tools aren't finding much. Let me work with what I have...)\"}\n\n"
                break

            if iteration == max_iterations - 1:
                yield "data: {\"type\":\"text\",\"content\":\"(Let me pull together what I found...)\"}\n\n"

        # Final synthesis if no natural response yet
        if not any(m.get("role") == "assistant" and m.get("content") for m in messages[-6:]):
            messages.append({
                "role": "system",
                "content": "Synthesize a natural response based on all collected info. No tools. Be direct."
            })
            providers = await LLMProvider._get_available_providers()
            synth_content = ""
            for provider, model, key in providers:
                try:
                    actual_model = "deepseek/deepseek-chat" if provider == "deepseek" else f"{provider}/{model}"
                    resp = await acompletion(
                        model=actual_model, messages=messages, api_key=key,
                        temperature=0.3, max_tokens=1000,
                    )
                    synth_content = resp.choices[0].message.content or ""
                    if synth_content:
                        break
                except Exception as e:
                    logger.warning("synthesis_failed", provider=provider, error=str(e)[:100])
                    continue

            if synth_content:
                yield f"data: {json.dumps({'type': 'text', 'content': synth_content})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'text', 'content': '(I checked the codebase but need more context to give you a thorough answer. Try asking about a specific file or function!)'})}\n\n"

        if total_tokens_in > 0:
            pricing = {"deepseek": (0.014, 0.028), "openai": (0.15, 0.60), "anthropic": (0.30, 1.50), "groq": (0.0, 0.0)}
            rate_in, rate_out = pricing.get(used_provider, (0.014, 0.028))
            total_cost = int(total_tokens_in * rate_in / 1000 * 100) + int(total_tokens_out * rate_out / 1000 * 100)
            try:
                await log_cost(used_provider, used_model_name, "chat", total_tokens_in, total_tokens_out, total_cost)
            except Exception:
                pass
            try:
                await log_audit(
                    "chat_query", "conversation", "",
                    f"Chat: {user_message[:80]}", llm_call_count,
                    total_tokens_in + total_tokens_out, total_cost, "success",
                )
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
        name = f"teammatex/{args['name']}" if not args['name'].startswith("teammatex/") else args['name']
        ref = await loop.run_in_executor(
            None, lambda: create_branch("/data/repos", name, args.get("base", "main")),
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
            from app.services.integrations.github import GitHubProvider
            provider = GitHubProvider(token=token)
            repo_name = args.get("repo_name", "")
            state = args.get("state", "open")
            limit = args.get("limit", 10)
            try:
                prs = await provider.list_prs(repo_name, state)
                prs = prs[:limit]
                return {"repo": repo_name, "count": len(prs), "prs": [{"number": p.number, "title": p.title, "url": p.url} for p in prs]}
            except Exception as e:
                return {"error": f"Failed to list PRs: {str(e)}"}
            finally:
                await provider.close()
        elif tool_name == "run_command":
            import subprocess
            loop = asyncio.get_running_loop()
            timeout = args.get("timeout", 15)
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
