"""Cost calculation: litellm's per-model price map, with a corrected fallback
for models litellm doesn't ship (e.g. deepseek-v4-flash), in fractional cents."""
from app.services.agent.cost import cost_cents


def test_known_model_uses_litellm_price():
    # litellm prices deepseek-chat at $0.28/1M in, $0.42/1M out.
    c = cost_cents("deepseek-chat", 1_000_000, 1_000_000)
    assert round(c, 4) == 70.0  # ($0.28 + $0.42) = $0.70 = 70 cents


def test_unknown_model_falls_back_to_provider_rate():
    # deepseek-v4-flash is NOT in litellm's map → fall back to the deepseek rate.
    c = cost_cents("deepseek-v4-flash", 1_000_000, 0, provider="deepseek")
    assert round(c, 4) == 28.0  # $0.28 = 28 cents


def test_sub_cent_cost_is_not_truncated():
    # The whole point of the fix: a tiny real cost survives as a fraction of a cent.
    c = cost_cents("deepseek-chat", 1000, 0)  # 1000 * 2.8e-7 * 100
    assert 0 < c < 1
    assert round(c, 5) == 0.028


def test_unpriceable_model_is_zero():
    assert cost_cents("mystery-model-9000", 1000, 1000) == 0.0
