"""Tests for agent.message_utils — correct OpenAI tool-call message format
and defensive stripping of leaked model tool-call markup (the DSML garbage)."""

from types import SimpleNamespace

from app.services.agent.message_utils import (
    assistant_tool_calls_message,
    serialize_tool_call,
    strip_tool_markup,
    tool_result_message,
)


def _fake_tc(tid, name, args):
    """Mimic a litellm ChatCompletionMessageToolCall object."""
    return SimpleNamespace(
        id=tid,
        type="function",
        function=SimpleNamespace(name=name, arguments=args),
    )


class TestSerializeToolCall:
    def test_serializes_object_to_plain_dict(self):
        tc = _fake_tc("call_1", "read_file", '{"file_path": "/a"}')
        assert serialize_tool_call(tc) == {
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"file_path": "/a"}'},
        }

    def test_handles_dict_input(self):
        d = {"id": "x", "type": "function", "function": {"name": "bash", "arguments": "{}"}}
        assert serialize_tool_call(d)["function"]["name"] == "bash"

    def test_non_string_arguments_become_json(self):
        tc = _fake_tc("c", "bash", {"command": "ls"})
        out = serialize_tool_call(tc)
        assert out["function"]["arguments"] == '{"command": "ls"}'


class TestAssistantMessage:
    def test_groups_all_tool_calls_into_one_message(self):
        tc1 = _fake_tc("call_1", "read_file", '{"file_path": "/a"}')
        tc2 = _fake_tc("call_2", "bash", '{"command": "ls"}')
        msg = assistant_tool_calls_message([tc1, tc2])
        assert msg["role"] == "assistant"
        assert msg["content"] is None
        assert len(msg["tool_calls"]) == 2
        assert msg["tool_calls"][0]["id"] == "call_1"
        assert msg["tool_calls"][1]["function"]["name"] == "bash"

    def test_tool_calls_are_plain_dicts(self):
        msg = assistant_tool_calls_message([_fake_tc("c", "bash", "{}")])
        assert isinstance(msg["tool_calls"][0], dict)
        assert isinstance(msg["tool_calls"][0]["function"], dict)

    def test_reasoning_content_included_when_present(self):
        # DeepSeek thinking models require reasoning_content be echoed back.
        msg = assistant_tool_calls_message(
            [_fake_tc("c", "bash", "{}")], reasoning_content="let me think"
        )
        assert msg["reasoning_content"] == "let me think"

    def test_reasoning_content_omitted_when_absent(self):
        msg = assistant_tool_calls_message([_fake_tc("c", "bash", "{}")])
        assert "reasoning_content" not in msg


class TestToolResultMessage:
    def test_shape(self):
        assert tool_result_message("call_1", '{"ok": true}') == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"ok": true}',
        }


class TestStripToolMarkup:
    # The exact garbage observed leaking to users from DeepSeek's synthesis turn.
    LEAKED = (
        "<｜｜DSML｜｜tool_calls>\n"
        '<｜｜DSML｜｜invoke name="run_command">\n'
        '<｜｜DSML｜｜parameter name="command" string="true">'
        'cd /data/repos/kit-fork && git add README.md && git commit -m "x"'
        "</｜｜DSML｜｜parameter>\n"
        "</｜｜DSML｜｜invoke>\n"
        "</｜｜DSML｜｜tool_calls>"
    )

    def test_removes_full_dsml_block(self):
        assert strip_tool_markup(self.LEAKED) == ""

    def test_preserves_normal_prose(self):
        text = "Here is your answer. No markup here."
        assert strip_tool_markup(text) == text

    def test_strips_block_but_keeps_surrounding_prose(self):
        mixed = "I committed the change.\n\n" + self.LEAKED
        assert strip_tool_markup(mixed) == "I committed the change."

    def test_removes_unclosed_trailing_block(self):
        # Model cut off mid tool-call: drop from the opening marker to the end.
        partial = "Done.\n\n<｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="
        assert strip_tool_markup(partial) == "Done."

    def test_strips_deepseek_native_special_tokens(self):
        native = "ok<｜tool▁calls▁begin｜>blah<｜tool▁calls▁end｜>"
        assert strip_tool_markup(native) == "ok"

    def test_none_passthrough(self):
        assert strip_tool_markup(None) is None
