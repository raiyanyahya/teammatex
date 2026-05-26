from typing import Any, AsyncIterator

from litellm import acompletion, completion_cost
from structlog import get_logger

from app.config import settings

logger = get_logger(__name__)

FALLBACK_CHAIN = [
    ("anthropic", settings.anthropic_model),
    ("openai", settings.openai_model),
    ("deepseek", settings.deepseek_model),
    ("groq", settings.groq_model),
    ("ollama", settings.ollama_model),
]

# Curated current models per provider. DeepSeek is the cheap default; Claude/GPT
# are higher tool-calling reliability for harder work. Switch the active model by
# saving an llm_config row: PUT /api/config/llm_config {provider, api_key, model}.
RECOMMENDED_MODELS = {
    "deepseek": [
        {"model": "deepseek-v4-flash", "tier": "cheap-default", "note": "Fast, non-thinking — best for tool loops."},
        {"model": "deepseek-v4-pro", "tier": "balanced", "note": "Thinking model; stronger reasoning, higher cost/latency."},
    ],
    "anthropic": [
        {"model": "claude-sonnet-4-6", "tier": "high-reliability", "note": "Excellent tool calling; recommended upgrade."},
        {"model": "claude-opus-4-7", "tier": "max", "note": "Most capable; highest cost."},
        {"model": "claude-haiku-4-5-20251001", "tier": "cheap", "note": "Fast, inexpensive Claude."},
    ],
    "openai": [
        {"model": "gpt-4o", "tier": "high-reliability", "note": "Strong, reliable tool calling."},
    ],
    "groq": [
        {"model": "llama-3.1-70b-versatile", "tier": "cheap", "note": "Fast hosted open model."},
    ],
    "ollama": [
        {"model": "llama3.1:8b", "tier": "local", "note": "Runs locally; no API key needed."},
    ],
}


class LLMProvider:
    _db_config_cache: dict | None = None

    @classmethod
    async def _get_db_config(cls) -> dict | None:
        try:
            from sqlalchemy import select
            from app.db.session import _init_engine
            from app.models.app_config import AppConfig
            _init_engine()
            from app.db.session import async_session_factory
            async with async_session_factory() as db:
                result = await db.execute(select(AppConfig).where(AppConfig.key == "llm_config"))
                row = result.scalar_one_or_none()
                if row and row.value:
                    return row.value
        except Exception:
            pass
        return None

    @classmethod
    def _get_api_key(cls, provider: str) -> str:
        env_map = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "deepseek": settings.deepseek_api_key,
            "groq": settings.groq_api_key,
            "ollama": settings.ollama_base_url,
        }
        env_key = env_map.get(provider, "")
        if env_key:
            return env_key
        # Fallback to DB config
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                db_cfg = asyncio.ensure_future(cls._get_db_config())
                # Can't await in sync context, return env key for now
                return env_key
        except Exception:
            pass
        return env_key

    @classmethod
    async def _get_available_providers(cls) -> list[tuple[str, str, str]]:
        """Returns list of (provider, model, api_key) for available providers."""
        providers: list[tuple[str, str, str]] = []
        env_map = {
            "anthropic": (settings.anthropic_api_key, settings.anthropic_model),
            "openai": (settings.openai_api_key, settings.openai_model),
            "deepseek": (settings.deepseek_api_key, settings.deepseek_model),
            "groq": (settings.groq_api_key, settings.groq_model),
            "ollama": (settings.ollama_base_url, settings.ollama_model),
        }

        # Check DB config first for any provider
        db_cfg = await cls._get_db_config()
        db_provider = db_cfg.get("provider") if db_cfg else None
        db_key = db_cfg.get("api_key") if db_cfg else None
        db_model = db_cfg.get("model") if db_cfg else None

        for provider, (env_key, env_model) in env_map.items():
            key = env_key
            model = env_model
            if provider == db_provider and db_key:
                key = db_key
                model = db_model or env_model
            if key:
                providers.append((provider, model, key))

        if not providers and db_key and db_provider:
            providers.append((db_provider, db_model or "default", db_key))

        if not providers:
            from app.config import settings as s
            providers.append(("ollama", "llama3.1:8b", s.ollama_base_url or "http://localhost:11434"))

        return providers

    @classmethod
    def _get_model_name(cls, provider: str, model: str) -> str:
        mapping = {
            "anthropic": f"anthropic/{model}",
            "openai": model,
            "deepseek": f"deepseek/{model}",
            "groq": f"groq/{model}",
            "ollama": f"ollama/{model}",
        }
        return mapping.get(provider, model)

    @classmethod
    async def chat(
        cls, messages: list[dict], temperature: float = 0.2,
        max_tokens: int = 4096, stream: bool = False, tools: list[dict] | None = None,
    ) -> dict:
        providers = await cls._get_available_providers()
        last_error = None

        for provider, model, api_key in providers:
            actual_model = cls._get_model_name(provider, model)
            kwargs: dict[str, Any] = {
                "model": actual_model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens,
                "api_key": api_key,
            }
            if tools:
                kwargs["tools"] = tools
            try:
                response = await acompletion(**kwargs)
                try:
                    cost = completion_cost(completion_response=response)
                except Exception:
                    cost = 0.0
                logger.debug("llm_call", provider=provider, model=model, cost=cost)
                return {
                    "content": response.choices[0].message.content or "",
                    "role": response.choices[0].message.role,
                    "model": model,
                    "provider": provider,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    },
                    "cost_cents": int(cost * 100) if cost else 0,
                    "tool_calls": getattr(response.choices[0].message, "tool_calls", None),
                }
            except Exception as e:
                logger.warning("llm_provider_failed", provider=provider, error=str(e))
                last_error = e
                continue
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    @classmethod
    async def chat_stream(
        cls, messages: list[dict], temperature: float = 0.2, max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        providers = await cls._get_available_providers()
        last_error = None
        for provider, model, api_key in providers:
            actual_model = cls._get_model_name(provider, model)
            try:
                response = await acompletion(
                    model=actual_model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens, api_key=api_key,
                    stream=True,
                )
                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return
            except Exception as e:
                logger.warning("llm_stream_failed", provider=provider, error=str(e))
                last_error = e
                continue
        raise RuntimeError(f"All streaming providers failed: {last_error}")

    @classmethod
    async def simple_prompt(cls, system: str, user: str, temperature: float = 0.2) -> str:
        result = await cls.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=temperature)
        return result["content"]
