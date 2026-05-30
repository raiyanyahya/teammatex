# Eval Harness + Citations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the source files the agent consulted as citations under each chat answer, and add a deterministic eval harness that scores retrieval quality (hit@k + MRR) over a self-contained fixture repo.

**Architecture:** A pure `citations.extract_sources()` turns the agent loop's tool activity into a deduped source list, which the loop emits as a new `sources` SSE event; the chat UI renders it. A separate `app/evals/` package scores the retrieval primitive (`EmbeddingService.search`) directly — deterministic, no LLM — against a golden Q→expected-file set, using a tiny fixture repo embedded into the test DB.

**Tech Stack:** FastAPI, SQLAlchemy async, pgvector, local MiniLM embeddings, pytest/pytest-asyncio, Next.js (chat UI).

---

## Environment for running tests

All backend tests run inside the api container (the prod image omits test deps):

```bash
docker compose exec api pip install -q pytest pytest-asyncio   # once per container
# copy edited files in during the loop (code is baked, not bind-mounted):
docker cp backend/<path> teammatex-api-1:/app/<path>
docker compose exec api python -m pytest <args>
```

The pure tests (citations, scoring) need no DB. The end-to-end eval test (Task 6) needs the test Postgres + local embedding model, via the `async_db` fixture in `conftest.py`.

---

## File Structure

**Create**
- `backend/app/services/agent/citations.py` — pure: tool activity → source list.
- `backend/app/evals/__init__.py` — package marker + re-exports.
- `backend/app/evals/engine.py` — scoring (hit@k, MRR) + `run_eval`.
- `backend/app/evals/fixtures.py` — load/embed the fixture repo into a db.
- `backend/app/evals/__main__.py` — CLI runner (threshold → exit code).
- `backend/app/evals/golden/fixture.yaml` — golden Q&A for the fixture repo.
- `backend/tests/fixtures/eval_repo/{auth.py,billing_webhooks.py,queue_retry.py,users.py,README.md}` — synthetic corpus.
- `backend/tests/test_citations.py` — citation extraction + loop emission.
- `backend/tests/test_evals.py` — scoring math + end-to-end fixture run.
- `frontend/src/components/chat/Sources.tsx` — renders a sources list.

**Modify**
- `backend/app/services/agent/loop.py` — accumulate tool invocations, emit `sources` event.
- `frontend/src/app/chat/page.tsx` — handle `sources` SSE event, attach to assistant message, render `Sources`.

---

## Task 1: Citation extraction (pure)

**Files:**
- Create: `backend/app/services/agent/citations.py`
- Test: `backend/tests/test_citations.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_citations.py
from app.services.agent.citations import extract_sources


def _env(data):
    """execute_tool wraps tool output as {"success": True, "data": ...}."""
    return {"success": True, "data": data}


def test_semantic_search_yields_file_sources_with_lines():
    invs = [{
        "tool": "semantic_search",
        "args": {"query": "stripe webhook"},
        "result": _env([
            {"file_path": "billing_webhooks.py", "start_line": 10, "end_line": 40},
            {"file_path": "auth.py", "start_line": 1, "end_line": 5},
        ]),
    }]
    out = extract_sources(invs)
    assert out == [
        {"path": "billing_webhooks.py", "tool": "semantic_search", "lines": "10-40"},
        {"path": "auth.py", "tool": "semantic_search", "lines": "1-5"},
    ]


def test_file_arg_tools_cite_the_path_argument():
    invs = [
        {"tool": "read_file", "args": {"file_path": "queue_retry.py"}, "result": _env({"content": "..."})},
        {"tool": "find_owner", "args": {"file_path": "auth.py"}, "result": _env({"owner": "maya"})},
    ]
    out = extract_sources(invs)
    assert {"path": "queue_retry.py", "tool": "read_file"} in out
    assert {"path": "auth.py", "tool": "find_owner"} in out


def test_dedup_by_path_keeps_first_and_skips_non_source_tools():
    invs = [
        {"tool": "semantic_search", "args": {}, "result": _env([{"file_path": "auth.py", "start_line": 1, "end_line": 9}])},
        {"tool": "read_file", "args": {"file_path": "auth.py"}, "result": _env({"content": "x"})},
        {"tool": "run_command", "args": {"command": "ls"}, "result": _env({"stdout": "auth.py"})},
    ]
    out = extract_sources(invs)
    assert [s["path"] for s in out] == ["auth.py"]          # deduped, run_command ignored
    assert out[0]["tool"] == "semantic_search"               # first wins (has line range)


def test_errored_tool_calls_produce_no_sources():
    invs = [{"tool": "read_file", "args": {"file_path": "x.py"}, "result": {"error": "File not found"}}]
    assert extract_sources(invs) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker cp backend/tests/test_citations.py teammatex-api-1:/app/tests/test_citations.py
docker compose exec api python -m pytest tests/test_citations.py -q
```
Expected: FAIL — `ModuleNotFoundError: app.services.agent.citations`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/agent/citations.py
"""Turn an agent turn's tool activity into a deduped, ordered list of the source
files it consulted — the data behind the chat answer's 'Sources' list and the
eval harness's notion of what was retrieved.

Pure: input is a list of {"tool", "args", "result"} dicts (result is the
execute_tool envelope {"success": True, "data": ...}); output is Source dicts.
No DB, no LLM.
"""
from __future__ import annotations

# Tools whose `file_path` argument names a specific source file.
_FILE_ARG_TOOLS = {"read_file", "edit_file", "write_file", "get_blame", "find_owner"}


def _unwrap(result):
    if isinstance(result, dict) and result.get("success") and "data" in result:
        return result["data"]
    return None  # errors / unknown shapes contribute no sources


def extract_sources(invocations: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()

    def add(path, tool, lines=None):
        if not path or not isinstance(path, str) or path in seen:
            return
        seen.add(path)
        src = {"path": path, "tool": tool}
        if lines:
            src["lines"] = lines
        sources.append(src)

    for inv in invocations:
        tool = inv.get("tool")
        args = inv.get("args") or {}
        data = _unwrap(inv.get("result"))

        if tool == "semantic_search" and isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("file_path"):
                    lines = None
                    if item.get("start_line") and item.get("end_line"):
                        lines = f"{item['start_line']}-{item['end_line']}"
                    add(item["file_path"], tool, lines)
        elif tool in _FILE_ARG_TOOLS:
            add(args.get("file_path") or args.get("path"), tool)

    return sources
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker cp backend/app/services/agent/citations.py teammatex-api-1:/app/app/services/agent/citations.py
docker compose exec api python -m pytest tests/test_citations.py -q
```
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/citations.py backend/tests/test_citations.py
git commit -m "feat(agent): pure citation extraction from tool activity"
```

---

## Task 2: Emit the `sources` event from the agent loop

**Files:**
- Modify: `backend/app/services/agent/loop.py`
- Test: `backend/tests/test_citations.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_citations.py
import pytest
from app.services.agent.loop import run_agent_loop


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = None


class _Resp:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]


class _TC:
    def __init__(self, name, args):
        self.id = "call_1"
        self.function = type("F", (), {"name": name, "arguments": args})()


@pytest.mark.asyncio
async def test_loop_emits_sources_event_after_answer():
    # Turn 1: one semantic_search tool call. Turn 2: a plain-text answer.
    responses = [
        _Resp(_Msg(tool_calls=[_TC("semantic_search", '{"query": "stripe"}')])),
        _Resp(_Msg(content="Webhooks are verified in billing_webhooks.py.")),
    ]
    calls = iter(responses)

    async def llm_call(messages, tools):
        return next(calls)

    async def execute_tool(name, args):
        return {"success": True, "data": [{"file_path": "billing_webhooks.py", "start_line": 1, "end_line": 9}]}

    events = [ev async for ev in run_agent_loop(
        llm_call=llm_call, execute_tool=execute_tool, messages=[], tools=[])]

    types = [e["type"] for e in events]
    assert "sources" in types
    sources_ev = next(e for e in events if e["type"] == "sources")
    assert sources_ev["sources"] == [
        {"path": "billing_webhooks.py", "tool": "semantic_search", "lines": "1-9"}]
    # sources must come after the final text answer
    assert types.index("sources") > types.index("text")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker cp backend/tests/test_citations.py teammatex-api-1:/app/tests/test_citations.py
docker compose exec api python -m pytest tests/test_citations.py::test_loop_emits_sources_event_after_answer -q
```
Expected: FAIL — no `sources` event in the stream.

- [ ] **Step 3: Modify the loop**

In `backend/app/services/agent/loop.py`, add the import near the top (after the existing `.message_utils` import):

```python
from .citations import extract_sources
```

Inside `run_agent_loop`, immediately after `nudges = 0` (before the `for` loop), add:

```python
    invocations: list[dict] = []

    def _sources_event() -> dict:
        return {"type": "sources", "sources": extract_sources(invocations)}
```

In the tool-calls branch, record each successful call. Change the `try` block so it reads:

```python
                try:
                    result = await execute_tool(name, args)
                    invocations.append({"tool": name, "args": args, "result": result})
                    result_str = json.dumps(result)[:4000]
                except Exception as e:  # tool failures are data, not crashes
                    result_str = json.dumps({"error": str(e)})
```

Emit the sources event before each terminal `return` that follows an answer. Update the three terminal points:

```python
        # No tool calls → the model is trying to answer.
        clean = strip_tool_markup(content or "")
        if clean:
            messages.append({"role": "assistant", "content": clean})
            yield {"type": "text", "content": clean}
            yield _sources_event()
            return
```

```python
        yield {"type": "text", "content": _EMPTY_MESSAGE}
        yield _sources_event()
        return
```

```python
        if clean:
            yield {"type": "text", "content": clean}
            yield _sources_event()
            return
    yield {"type": "text", "content": _CAP_MESSAGE}
    yield _sources_event()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
docker cp backend/app/services/agent/loop.py teammatex-api-1:/app/app/services/agent/loop.py
docker compose exec api python -m pytest tests/test_citations.py tests/test_agent_loop.py -q
```
Expected: PASS (new test passes; existing `test_agent_loop.py` still green — extra trailing event doesn't break its assertions; if any loop test counts events exactly, update it to expect the trailing `sources` event).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/loop.py backend/tests/test_citations.py
git commit -m "feat(agent): emit sources event with answer citations"
```

---

## Task 3: Render citations in the chat UI

**Files:**
- Create: `frontend/src/components/chat/Sources.tsx`
- Modify: `frontend/src/app/chat/page.tsx`

- [ ] **Step 1: Create the Sources component**

```tsx
// frontend/src/components/chat/Sources.tsx
type Source = { path: string; tool: string; lines?: string };

export default function Sources({ sources }: { sources?: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed var(--line-strong)", paddingTop: 8 }}>
      <div className="font-mono" style={{ fontSize: 10, letterSpacing: "0.1em", color: "var(--paper-4)", marginBottom: 6 }}>
        SOURCES
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {sources.map((s, i) => (
          <div key={i} className="font-mono" style={{ fontSize: 11, color: "var(--paper-2)" }}>
            <span style={{ color: "var(--sky)" }}>{s.path}</span>
            {s.lines ? <span style={{ color: "var(--paper-4)" }}>:{s.lines}</span> : null}
            <span style={{ color: "var(--paper-4)" }}> · {s.tool}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Extend the Message type** in `frontend/src/app/chat/page.tsx`:

```tsx
type Source = { path: string; tool: string; lines?: string };

interface Message {
  role: Role;
  content: string;
  tool?: string;
  args?: string;
  result?: string;
  sources?: Source[];
}
```

- [ ] **Step 3: Capture the sources event.** In the SSE loop in `page.tsx`, declare a holder alongside `accumulated`/`toolMessages` (near the top of the streaming function):

```tsx
    let sources: Source[] = [];
```

Add a branch in the event switch (after the `tool_end` branch):

```tsx
            } else if (data.type === "sources") {
              sources = Array.isArray(data.sources) ? data.sources : [];
            }
```

In the `finally` block, attach sources to the assistant message:

```tsx
      if (accumulated) {
        setMessages((prev) => [...prev, ...toolMessages, { role: "assistant", content: accumulated, sources }]);
      }
```

- [ ] **Step 4: Render it.** Import the component at the top of `page.tsx`:

```tsx
import Sources from "../../components/chat/Sources";
```

Where an assistant message's content is rendered, add `<Sources sources={m.sources} />` immediately after the content block.

- [ ] **Step 5: Verify the build + a live smoke test**

Run:
```bash
docker compose build frontend && docker compose up -d frontend
```
Then log in, ask the chat a code question against an onboarded repo, and confirm a "SOURCES" list appears under the answer listing the files it searched/read. (Use the headless-login screenshot pattern from earlier sessions if driving it programmatically.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/Sources.tsx frontend/src/app/chat/page.tsx
git commit -m "feat(chat): render answer citations (Sources)"
```

---

## Task 4: Eval scoring core (pure)

**Files:**
- Create: `backend/app/evals/__init__.py`, `backend/app/evals/engine.py`
- Test: `backend/tests/test_evals.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_evals.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker cp backend/tests/test_evals.py teammatex-api-1:/app/tests/test_evals.py
docker compose exec api python -m pytest tests/test_evals.py -q
```
Expected: FAIL — `ModuleNotFoundError: app.evals`.

- [ ] **Step 3: Write the engine**

```python
# backend/app/evals/__init__.py
from .engine import score_item, aggregate, run_eval  # noqa: F401
```

```python
# backend/app/evals/engine.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker cp backend/app/evals/__init__.py teammatex-api-1:/app/app/evals/__init__.py
docker cp backend/app/evals/engine.py teammatex-api-1:/app/app/evals/engine.py
docker compose exec api python -m pytest tests/test_evals.py -q
```
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/evals/__init__.py backend/app/evals/engine.py backend/tests/test_evals.py
git commit -m "feat(evals): deterministic retrieval scoring (hit@k, MRR)"
```

---

## Task 5: Fixture corpus + golden set

**Files:**
- Create: `backend/tests/fixtures/eval_repo/{auth.py,billing_webhooks.py,queue_retry.py,users.py,README.md}`
- Create: `backend/app/evals/golden/fixture.yaml`

- [ ] **Step 1: Create the synthetic repo files** (distinct, unambiguous content)

```python
# backend/tests/fixtures/eval_repo/auth.py
"""User authentication: password login and JWT token verification."""

def login(email: str, password: str) -> str:
    """Verify the user's password and return a signed session JWT."""
    ...

def verify_token(token: str) -> dict | None:
    """Decode and validate a session JWT; return its payload or None."""
    ...
```

```python
# backend/tests/fixtures/eval_repo/billing_webhooks.py
"""Stripe billing webhooks: verify signatures and process payment events."""

def verify_stripe_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Validate the Stripe-Signature header against the webhook secret."""
    ...

def handle_invoice_paid(event: dict) -> None:
    """Mark the subscription active when an invoice.paid webhook arrives."""
    ...
```

```python
# backend/tests/fixtures/eval_repo/queue_retry.py
"""Task queue retry policy: exponential backoff for failed jobs."""

def retry_with_backoff(job, max_attempts: int = 3) -> None:
    """Re-run a failed job with exponentially increasing delay."""
    ...
```

```python
# backend/tests/fixtures/eval_repo/users.py
"""User CRUD: create, fetch, update, and deactivate user records."""

def create_user(email: str, name: str) -> dict:
    """Insert a new user row and return it."""
    ...

def deactivate_user(user_id: str) -> None:
    """Soft-delete a user by marking them inactive."""
    ...
```

```markdown
<!-- backend/tests/fixtures/eval_repo/README.md -->
# Example Service

A demo service with authentication, Stripe billing, a retrying task queue, and user management.
```

- [ ] **Step 2: Create the golden set**

```yaml
# backend/app/evals/golden/fixture.yaml
repo: eval-fixture
questions:
  - id: q1
    question: "How do we verify Stripe webhook signatures?"
    expect_files: ["billing_webhooks.py"]
  - id: q2
    question: "Where is the password login and JWT verification?"
    expect_files: ["auth.py"]
  - id: q3
    question: "How are failed jobs retried with backoff?"
    expect_files: ["queue_retry.py"]
  - id: q4
    question: "Where do we create and deactivate users?"
    expect_files: ["users.py"]
  - id: q5
    question: "How is a subscription marked active after payment?"
    expect_files: ["billing_webhooks.py"]
  - id: q6
    question: "How do we decode and validate a session token?"
    expect_files: ["auth.py"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/fixtures/eval_repo backend/app/evals/golden/fixture.yaml
git commit -m "test(evals): synthetic fixture repo + golden question set"
```

---

## Task 6: Fixture loader + end-to-end eval

**Files:**
- Create: `backend/app/evals/fixtures.py`
- Test: `backend/tests/test_evals.py` (append)

- [ ] **Step 1: Write the failing end-to-end test**

```python
# append to backend/tests/test_evals.py
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_fixture_retrieval_eval_meets_floor(async_db):
    from app.evals.fixtures import load_fixture_repo, load_golden
    from app.evals.engine import run_eval
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
    assert q1["rank"] == 1                       # the Stripe question hits its file first
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker cp backend/tests/test_evals.py teammatex-api-1:/app/tests/test_evals.py
docker compose exec api python -m pytest tests/test_evals.py::test_fixture_retrieval_eval_meets_floor -q
```
Expected: FAIL — `ModuleNotFoundError: app.evals.fixtures`.

- [ ] **Step 3: Write the loader**

```python
# backend/app/evals/fixtures.py
"""Load a synthetic fixture repo into a db via the REAL chunk+embed path, so the
eval exercises the actual retrieval stack (just small)."""
from __future__ import annotations

from pathlib import Path

import yaml

_LANG = {".py": "python", ".md": "markdown", ".js": "javascript", ".ts": "typescript", ".go": "go"}


async def load_fixture_repo(db, embedder, fixture_dir: Path, repo_id: str) -> int:
    """Chunk + embed every file under fixture_dir into code_embeddings for repo_id.
    Ensures the embeddings table dimension matches the active model first (the
    same self-healing the onboarding pipeline relies on)."""
    from app.services.knowledge.chunker import CodeChunker
    from app.services.knowledge.embedding_schema import ensure_embedding_dim

    await ensure_embedding_dim(db)  # align code_embeddings vector dim to the local model

    chunker = CodeChunker()
    total = 0
    for path in sorted(fixture_dir.iterdir()):
        if not path.is_file():
            continue
        content = path.read_text()
        lang = _LANG.get(path.suffix, "text")
        chunks = chunker.chunk(content, path.name, lang)
        total += await embedder.embed_and_store(db, chunks, repo_id=repo_id)
    return total


def load_golden(name: str) -> list[dict]:
    """Read app/evals/golden/<name> → list of {id, question, repo, expect_files}."""
    golden_path = Path(__file__).parent / "golden" / name
    doc = yaml.safe_load(golden_path.read_text())
    repo = doc["repo"]
    return [
        {"id": q["id"], "question": q["question"], "repo": repo, "expect_files": q["expect_files"]}
        for q in doc["questions"]
    ]
```

> **Note for the implementer:** confirm the exact name of the schema-reconcile helper in `app/services/knowledge/embedding_schema.py` (it may be `ensure_embedding_dim`, `reconcile_embedding_schema`, or similar) and the `CodeChunker.chunk(content, file_path, language)` signature; both already exist and are used by the onboarding pipeline. If `chunk()` returns no chunks for the tiny markdown file, that's fine — the `.py` files carry the retrievable content the golden set targets.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker cp backend/app/evals/fixtures.py teammatex-api-1:/app/app/evals/fixtures.py
docker compose exec api python -m pytest tests/test_evals.py -q
```
Expected: PASS. If a question misses, inspect `report` (printed on assert) and sharpen that file's docstring/wording so its content is the unambiguous match — do NOT weaken the floor below 0.8.

- [ ] **Step 5: Commit**

```bash
git add backend/app/evals/fixtures.py backend/tests/test_evals.py
git commit -m "test(evals): end-to-end fixture retrieval eval"
```

---

## Task 7: CLI runner with threshold gate

**Files:**
- Create: `backend/app/evals/__main__.py`
- Test: `backend/tests/test_evals.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_evals.py
def test_threshold_exit_code():
    from app.evals.__main__ import exit_code_for

    assert exit_code_for(summary={"hit_rate": 0.9}, threshold=0.8) == 0
    assert exit_code_for(summary={"hit_rate": 0.7}, threshold=0.8) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker cp backend/tests/test_evals.py teammatex-api-1:/app/tests/test_evals.py
docker compose exec api python -m pytest tests/test_evals.py::test_threshold_exit_code -q
```
Expected: FAIL — `ModuleNotFoundError: app.evals.__main__`.

- [ ] **Step 3: Write the CLI**

```python
# backend/app/evals/__main__.py
"""Run the retrieval eval and gate on a hit-rate threshold.

    python -m app.evals [--golden fixture.yaml] [--k 3] [--threshold 0.8]

Exits non-zero if hit_rate < threshold, so it can act as a regression gate."""
from __future__ import annotations

import argparse
import asyncio


def exit_code_for(summary: dict, threshold: float) -> int:
    return 0 if summary["hit_rate"] >= threshold else 1


def _print_report(report: dict) -> None:
    print(f"{'ID':<6} {'HIT':<4} {'RANK':<5} QUESTION")
    for it in report["items"]:
        print(f"{it['id']:<6} {'✓' if it['hit'] else '·':<4} {str(it['rank'] or '-'):<5} {it['question']}")
    s = report["summary"]
    print(f"\n{s['count']} questions · hit-rate: {s['hit_rate']:.2f} · MRR: {s['mrr']:.2f}")


async def _amain(args) -> int:
    from app.db.session import async_session_factory, _init_engine
    from app.evals.engine import run_eval
    from app.evals.fixtures import load_fixture_repo, load_golden
    from app.services.knowledge.embeddings import EmbeddingService
    from pathlib import Path

    _init_engine()
    embedder = EmbeddingService()
    golden = load_golden(args.golden)
    async with async_session_factory() as db:
        if args.golden == "fixture.yaml":
            fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "eval_repo"
            await load_fixture_repo(db, embedder, fixture_dir, "eval-fixture")
        report = await run_eval(db, embedder, golden, k=args.k)
    _print_report(report)
    return exit_code_for(report["summary"], args.threshold)


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.evals")
    p.add_argument("--golden", default="fixture.yaml")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--threshold", type=float, default=0.8)
    args = p.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
```

> **Note for the implementer:** confirm `app.db.session` exposes `async_session_factory` + `_init_engine` (the lifespan in `app/main.py` uses both). Adjust the import to the actual session-factory name if different.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker cp backend/app/evals/__main__.py teammatex-api-1:/app/app/evals/__main__.py
docker compose exec api python -m pytest tests/test_evals.py -q
```
Expected: PASS (all eval tests green).

- [ ] **Step 5: Smoke-run the CLI against the fixture**

Run:
```bash
docker compose exec api python -m app.evals --threshold 0.8; echo "exit: $?"
```
Expected: a report table printed, hit-rate ≥ 0.80, `exit: 0`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/evals/__main__.py backend/tests/test_evals.py
git commit -m "feat(evals): CLI runner with hit-rate threshold gate"
```

---

## Final verification

- [ ] Full backend suite green:
```bash
docker compose exec api python -m pytest tests/test_citations.py tests/test_evals.py tests/test_agent_loop.py tests/test_api.py -q
```
- [ ] Frontend builds: `docker compose build frontend`.
- [ ] Live: ask the chat a question on an onboarded repo → "SOURCES" appears under the answer.
- [ ] CLI gate works: `python -m app.evals` exits 0 with hit-rate ≥ 0.8.
- [ ] Rebuild images to persist (`docker compose build api frontend`).
