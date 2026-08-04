"""Accurate LLM cost calculation.

Single source of truth for "what did this call cost". Uses litellm's per-model
price map (the same data litellm bills with), and falls back to a corrected
per-token rate for models litellm doesn't ship a price for — notably
`deepseek-v4-flash`, which isn't in litellm's map.

Returns **fractional cents** so sub-cent costs (the norm for cheap models) are
not truncated to zero, which is what the old integer-cents math did.
"""

from __future__ import annotations

import litellm

# Real per-token USD rates (input, output) for models/providers litellm doesn't
# price. For any deepseek model missing from litellm's map, fall back to
# deepseek-chat's published rate ($0.28/1M in, $0.42/1M out).
_FALLBACK_RATES: dict[str, tuple[float, float]] = {
    "deepseek": (2.8e-7, 4.2e-7),
}


def _rates_for(model: str, provider: str = "") -> tuple[float, float]:
    """(input_per_token, output_per_token) USD. Prefer litellm's map (try the
    full name and the part after any `provider/` prefix); else a fallback rate
    matched by provider/model substring; else (0, 0) for genuinely unknown models."""
    entry = litellm.model_cost.get(model) or litellm.model_cost.get(model.split("/")[-1])
    if entry and entry.get("input_cost_per_token"):
        return entry["input_cost_per_token"], entry.get("output_cost_per_token") or 0.0

    hay = f"{provider} {model}".lower()
    for key, rate in _FALLBACK_RATES.items():
        if key in hay:
            return rate
    return 0.0, 0.0


def cost_cents(model: str, tokens_in: int, tokens_out: int, provider: str = "") -> float:
    """Cost of one LLM call in fractional cents, from its token counts."""
    rate_in, rate_out = _rates_for(model, provider)
    return (tokens_in * rate_in + tokens_out * rate_out) * 100.0
