"""Lock the litellm model-name mapping and the recommended-model registry,
so switching the agent to Claude/GPT for higher tool-calling reliability works
while DeepSeek stays the cheap default.
"""

from app.services.llm.provider import LLMProvider, RECOMMENDED_MODELS


def test_model_name_mapping_for_each_provider():
    assert LLMProvider._get_model_name("anthropic", "claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"
    assert LLMProvider._get_model_name("openai", "gpt-4o") == "gpt-4o"
    assert LLMProvider._get_model_name("deepseek", "deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    assert LLMProvider._get_model_name("groq", "llama-3.1-70b-versatile") == "groq/llama-3.1-70b-versatile"
    assert LLMProvider._get_model_name("ollama", "llama3.1:8b") == "ollama/llama3.1:8b"


def test_deepseek_is_the_cheap_default():
    tiers = [m["tier"] for m in RECOMMENDED_MODELS["deepseek"]]
    assert "cheap-default" in tiers


def test_stronger_providers_available():
    # Claude + GPT are offered as higher-reliability upgrades.
    assert "anthropic" in RECOMMENDED_MODELS
    assert "openai" in RECOMMENDED_MODELS
    anthropic_models = [m["model"] for m in RECOMMENDED_MODELS["anthropic"]]
    assert any(m.startswith("claude-") for m in anthropic_models)


def test_registry_entries_well_formed():
    for provider, models in RECOMMENDED_MODELS.items():
        assert models, f"{provider} has no models"
        for m in models:
            assert {"model", "tier", "note"} <= set(m)
