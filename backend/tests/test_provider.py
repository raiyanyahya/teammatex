"""Tests for LLMProvider: correct model-name mapping (use v4, not the
deprecated deepseek-chat) and that chat() doesn't crash on the success path
(the old code referenced an undefined `model_name`)."""

from types import SimpleNamespace

import pytest

from app.services.llm import provider as P


class TestModelName:
    def test_deepseek_v4_flash_passes_through(self):
        assert (
            P.LLMProvider._get_model_name("deepseek", "deepseek-v4-flash")
            == "deepseek/deepseek-v4-flash"
        )

    def test_deepseek_v4_pro_passes_through(self):
        assert (
            P.LLMProvider._get_model_name("deepseek", "deepseek-v4-pro")
            == "deepseek/deepseek-v4-pro"
        )

    def test_legacy_deepseek_chat_still_maps(self):
        assert (
            P.LLMProvider._get_model_name("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
        )

    def test_anthropic_prefixed(self):
        assert P.LLMProvider._get_model_name("anthropic", "claude-x") == "anthropic/claude-x"


@pytest.mark.asyncio
async def test_chat_returns_without_nameerror(monkeypatch):
    async def fake_providers(cls):
        return [("deepseek", "deepseek-v4-flash", "key")]

    async def fake_acompletion(**kw):
        msg = SimpleNamespace(content="hi", role="assistant", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    monkeypatch.setattr(P.LLMProvider, "_get_available_providers", classmethod(fake_providers))
    monkeypatch.setattr(P, "acompletion", fake_acompletion)
    monkeypatch.setattr(P, "completion_cost", lambda **kw: 0.0)

    out = await P.LLMProvider.chat([{"role": "user", "content": "hi"}])
    assert out["content"] == "hi"
    assert out["model"] == "deepseek-v4-flash"
    assert out["provider"] == "deepseek"
