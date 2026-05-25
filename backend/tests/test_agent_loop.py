"""Tests for the agent loop, isolated from litellm/DB via injected callables.

This is the unit that produced the user-visible failures:
- the loop ran out of iterations mid-PR and never finished;
- a no-tools "synthesis" turn leaked DeepSeek tool-call markup as the answer.

The loop yields event dicts; the HTTP layer serializes them to SSE.
"""

from types import SimpleNamespace

import pytest

from app.services.agent.loop import run_agent_loop


def _tc(tid, name, args):
    return SimpleNamespace(id=tid, type="function",
                           function=SimpleNamespace(name=name, arguments=args))


def _response(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _scripted_llm(responses):
    it = iter(responses)

    async def _call(messages, tools):
        return next(it, _response(content="(done)"))

    return _call


async def _ok_exec(name, args):
    return {"success": True, "data": f"ran {name} with {args}"}


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
class TestAgentLoop:
    async def test_tool_then_final_text(self):
        llm = _scripted_llm([
            _response(tool_calls=[_tc("c1", "read_file", '{"file_path": "/a"}')]),
            _response(content="The file says hello."),
        ])
        msgs = [{"role": "user", "content": "read /a"}]
        events = await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec, messages=msgs, tools=[{"x": 1}]))
        assert [e["type"] for e in events] == ["tool_start", "tool_end", "text"]
        assert events[-1]["content"] == "The file says hello."

    async def test_multiple_tool_calls_one_turn_all_run(self):
        llm = _scripted_llm([
            _response(tool_calls=[
                _tc("c1", "read_file", '{"file_path": "/a"}'),
                _tc("c2", "bash", '{"command": "ls"}'),
            ]),
            _response(content="done"),
        ])
        events = await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec,
            messages=[{"role": "user", "content": "go"}], tools=[]))
        starts = [e["tool"] for e in events if e["type"] == "tool_start"]
        assert starts == ["read_file", "bash"]

    async def test_message_history_has_grouped_assistant_then_tool_msgs(self):
        llm = _scripted_llm([
            _response(tool_calls=[
                _tc("c1", "read_file", "{}"), _tc("c2", "bash", "{}")]),
            _response(content="done"),
        ])
        msgs = [{"role": "user", "content": "go"}]
        await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec, messages=msgs, tools=[]))
        # one assistant message carrying BOTH tool calls, then two tool replies
        assistant = [m for m in msgs if m["role"] == "assistant" and m.get("tool_calls")]
        assert len(assistant) == 1
        assert len(assistant[0]["tool_calls"]) == 2
        tool_msgs = [m for m in msgs if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]

    async def test_leaked_markup_in_final_text_is_stripped(self):
        leaked = ('I committed it.\n\n<｜｜DSML｜｜tool_calls>\n'
                  '<｜｜DSML｜｜invoke name="bash"></｜｜DSML｜｜invoke>\n'
                  '</｜｜DSML｜｜tool_calls>')
        llm = _scripted_llm([_response(content=leaked)])
        events = await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec,
            messages=[{"role": "user", "content": "x"}], tools=[]))
        texts = [e["content"] for e in events if e["type"] == "text"]
        assert texts == ["I committed it."]
        # no event anywhere may contain raw markup
        assert all("DSML" not in str(e) for e in events)

    async def test_no_llm_response_yields_error(self):
        async def none_llm(messages, tools):
            return None
        events = await _collect(run_agent_loop(
            llm_call=none_llm, execute_tool=_ok_exec,
            messages=[{"role": "user", "content": "x"}], tools=[]))
        assert events[-1]["type"] == "error"

    async def test_iteration_cap_terminates_with_text(self):
        # Model always calls a tool — loop must stop and still emit a final text.
        async def always_tool(messages, tools):
            return _response(tool_calls=[_tc("c", "bash", "{}")])
        events = await _collect(run_agent_loop(
            llm_call=always_tool, execute_tool=_ok_exec,
            messages=[{"role": "user", "content": "x"}], tools=[],
            max_iterations=3))
        assert events[-1]["type"] == "text"
        # 3 iterations, each one tool call
        assert sum(1 for e in events if e["type"] == "tool_start") == 3

    async def test_cap_summarizes_instead_of_canned_message(self):
        # When the step limit is hit, do one final plain-text wrap-up call so
        # the user learns WHAT happened, not just "I ran out of steps".
        n = {"c": 0}

        async def llm(messages, tools):
            n["c"] += 1
            if n["c"] <= 3:
                return _response(tool_calls=[_tc("c", "bash", "{}")])
            return _response(content="Edited the file but push failed: 403 permission denied.")

        events = await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec,
            messages=[{"role": "user", "content": "x"}], tools=[], max_iterations=3))
        assert events[-1]["type"] == "text"
        assert "403" in events[-1]["content"]

    async def test_reasoning_content_preserved_in_history(self):
        # A thinking model returns reasoning_content alongside tool calls; it
        # must be echoed back or the next call 400s.
        def _resp_reasoning():
            msg = SimpleNamespace(content=None, reasoning_content="thinking...",
                                  tool_calls=[_tc("c", "bash", "{}")])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                                   usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
        llm = _scripted_llm([_resp_reasoning(), _response(content="done")])
        msgs = [{"role": "user", "content": "go"}]
        await _collect(run_agent_loop(
            llm_call=llm, execute_tool=_ok_exec, messages=msgs, tools=[]))
        assistant = [m for m in msgs if m["role"] == "assistant" and m.get("tool_calls")][0]
        assert assistant["reasoning_content"] == "thinking..."

    async def test_tool_execution_error_is_reported_not_fatal(self):
        async def boom_exec(name, args):
            raise RuntimeError("kaboom")
        llm = _scripted_llm([
            _response(tool_calls=[_tc("c", "bash", "{}")]),
            _response(content="recovered"),
        ])
        events = await _collect(run_agent_loop(
            llm_call=llm, execute_tool=boom_exec,
            messages=[{"role": "user", "content": "x"}], tools=[]))
        end = [e for e in events if e["type"] == "tool_end"][0]
        assert "kaboom" in end["result"]
        assert events[-1]["content"] == "recovered"
