"""Tests for the embedding-dimension single source of truth.

Regression guard for the bug where the table was vector(1536) while the local
model emits 384, so every insert failed the dimension check and was swallowed.
"""

from app.services.knowledge.embedding_schema import (
    LOCAL_DIM,
    OPENAI_DIM,
    expected_dim,
    parse_vector_dim,
)


def test_expected_dim_local_is_384():
    assert expected_dim("local") == LOCAL_DIM == 384


def test_expected_dim_openai_is_1536():
    assert expected_dim("openai") == OPENAI_DIM == 1536


def test_expected_dim_unknown_provider_defaults_to_openai_dim():
    # Any non-local provider uses the API embedding size.
    assert expected_dim("anthropic") == OPENAI_DIM


def test_parse_vector_dim_extracts_number():
    assert parse_vector_dim("vector(384)") == 384
    assert parse_vector_dim("vector(1536)") == 1536


def test_parse_vector_dim_handles_non_vector_types():
    assert parse_vector_dim("text") is None
    assert parse_vector_dim("") is None
    assert parse_vector_dim(None) is None
