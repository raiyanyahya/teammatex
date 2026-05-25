"""The agent's tool-calling loop, isolated from litellm and the database.

``llm_call`` and ``execute_tool`` are injected so the loop is fully unit
testable. It yields plain event dicts; the HTTP layer serializes them to SSE.

Design decisions that fix the observed bugs:

- **Always pass ``tools``** (the caller does this). The old code had a separate
  "synthesis" turn with no tools, which made DeepSeek dump its tool-call tokens
  as text — the ``<｜｜DSML｜｜…>`` garbage. There is no tool-less turn here.
- **Correct message format**: one assistant message carrying all tool calls,
  then one ``tool`` message each (via message_utils), with plain-dict tool calls.
- **Defensive strip** of any tool-call markup that still leaks into text.
- **Bounded but generous**: up to ``max_iterations`` turns so multi-step work
  (branch → edit → commit → push → PR) actually completes, and a clean wrap-up
  message if the cap is hit instead of trailing off mid-task.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from .message_utils import (
    assistant_tool_calls_message,
    strip_tool_markup,
    tool_result_message,
)

_CAP_MESSAGE = ("(I hit my step limit on this task. Tell me to keep going and "
                "I'll continue from where I left off.)")
_EMPTY_MESSAGE = ("(I couldn't produce a clean answer for that — try rephrasing "
                  "or giving me a bit more detail.)")
_NUDGE = ("Call tools using the function-calling interface, not by writing them "
          "as text. Otherwise reply with your final answer in plain prose.")
_WRAPUP = ("You've reached the step limit. In plain text, summarize what you "
           "accomplished and what (if anything) is blocking completion. Do not "
           "call any more tools.")


def _parse_args(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


async def run_agent_loop(
    *, llm_call, execute_tool, messages, tools,
    max_iterations: int = 25, max_tools_per_turn: int = 8,
) -> AsyncIterator[dict]:
    nudges = 0

    for _iteration in range(max_iterations):
        response = await llm_call(messages, tools)
        if response is None:
            yield {"type": "error", "content": "LLM unavailable — check provider keys."}
            return

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        content = getattr(msg, "content", None)

        if tool_calls:
            reasoning = getattr(msg, "reasoning_content", None)
            messages.append(assistant_tool_calls_message(tool_calls, reasoning))
            for tc in list(tool_calls)[:max_tools_per_turn]:
                name = tc.function.name
                args = _parse_args(tc.function.arguments)
                yield {"type": "tool_start", "tool": name, "args": str(args)[:200]}
                try:
                    result = await execute_tool(name, args)
                    result_str = json.dumps(result)[:4000]
                except Exception as e:  # tool failures are data, not crashes
                    result_str = json.dumps({"error": str(e)})
                yield {"type": "tool_end", "tool": name, "result": result_str[:500]}
                messages.append(tool_result_message(tc.id, result_str))
            continue

        # No tool calls → the model is trying to answer.
        clean = strip_tool_markup(content or "")
        if clean:
            messages.append({"role": "assistant", "content": clean})
            yield {"type": "text", "content": clean}
            return

        # Empty, or content was nothing but leaked tool-call markup.
        if (content or "").strip() and nudges < 2:
            nudges += 1
            messages.append({"role": "system", "content": _NUDGE})
            continue
        yield {"type": "text", "content": _EMPTY_MESSAGE}
        return

    # Step limit hit: one final plain-text wrap-up so the user learns what
    # happened and what's blocking, rather than a bare "ran out of steps".
    messages.append({"role": "system", "content": _WRAPUP})
    response = await llm_call(messages, tools)
    if response is not None:
        clean = strip_tool_markup(
            getattr(response.choices[0].message, "content", None) or "")
        if clean:
            yield {"type": "text", "content": clean}
            return
    yield {"type": "text", "content": _CAP_MESSAGE}
