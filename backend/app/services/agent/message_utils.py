"""Helpers for building correctly-formatted OpenAI chat messages from model
tool-call responses, and for defensively stripping leaked tool-call markup.

Two bugs motivated this module:

1. The old loop appended one assistant message *per* tool call, breaking the
   OpenAI contract (one assistant message carries ALL tool_calls, each answered
   by a following ``tool`` message). It also stuffed raw litellm pydantic
   objects into the history, which don't round-trip cleanly.

2. When the model wanted to call a tool but was given no ``tools=``, DeepSeek
   emitted its native tool-call tokens as plain text — the ``<｜｜DSML｜｜…>``
   garbage users saw. We now always pass tools, but we also strip any markup
   that leaks through as a last line of defence.
"""

from __future__ import annotations

import json
import re

# DeepSeek special-token marker: fullwidth vertical line U+FF5C (｜).
_FW = "｜"

# Full leaked tool-call blocks (open marker → matching close, or to end of
# string if the model was cut off mid-call). DOTALL so they span newlines.
_BLOCK_PATTERNS = [
    # DSML XML-ish variant: <｜｜DSML｜｜tool_calls> … </｜｜DSML｜｜tool_calls>
    re.compile(
        r"<｜+DSML｜+tool_calls>.*?(?:</｜+DSML｜+tool_calls>|$)",
        re.DOTALL,
    ),
    # DeepSeek native: <｜tool▁calls▁begin｜> … <｜tool▁calls▁end｜>
    # (▁ is U+2581; tolerate _ or space variants too)
    re.compile(
        r"<｜tool[▁_ ]calls[▁_ ]begin｜>.*?" r"(?:<｜tool[▁_ ]calls[▁_ ]end｜>|$)",
        re.DOTALL,
    ),
]

# Any leftover stray special-token tag using the fullwidth bar.
_STRAY = re.compile(r"</?｜[^>]*>")


def serialize_tool_call(tc) -> dict:
    """Convert a litellm tool-call object (or dict) to a plain OpenAI dict."""
    if isinstance(tc, dict):
        fn = tc.get("function", {}) or {}
        name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
        args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
        tid = tc.get("id")
    else:
        name = tc.function.name
        args = tc.function.arguments
        tid = tc.id
    if not isinstance(args, str):
        args = json.dumps(args or {})
    return {"id": tid, "type": "function", "function": {"name": name, "arguments": args}}


def assistant_tool_calls_message(tool_calls, reasoning_content=None) -> dict:
    """One assistant message carrying ALL tool calls, as plain dicts.

    ``reasoning_content`` (from DeepSeek thinking models) is echoed back when
    present — those models 400 on the next call if it isn't returned.
    """
    msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [serialize_tool_call(tc) for tc in tool_calls],
    }
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    return msg


def tool_result_message(tool_call_id: str, content: str) -> dict:
    """The ``tool`` message answering a single tool call."""
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def strip_tool_markup(text):
    """Remove leaked model tool-call markup from text meant for the user."""
    if not text:
        return text
    for pat in _BLOCK_PATTERNS:
        text = pat.sub("", text)
    text = _STRAY.sub("", text)
    return text.strip()
