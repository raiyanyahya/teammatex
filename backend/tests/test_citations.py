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
