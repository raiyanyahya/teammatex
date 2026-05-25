"""Tests for the real web_search backend: provider selection by env key and
normalization of each provider's raw results into a single shape."""

from app.services.agent.web_search import normalize_results, select_search_provider


class TestProviderSelection:
    def test_defaults_to_duckduckgo_with_no_keys(self):
        assert select_search_provider({}) == "duckduckgo"

    def test_tavily_when_key_present(self):
        assert select_search_provider({"TAVILY_API_KEY": "x"}) == "tavily"

    def test_brave_when_key_present(self):
        assert select_search_provider({"BRAVE_API_KEY": "x"}) == "brave"

    def test_tavily_preferred_over_brave(self):
        env = {"TAVILY_API_KEY": "x", "BRAVE_API_KEY": "y"}
        assert select_search_provider(env) == "tavily"

    def test_empty_key_ignored(self):
        assert select_search_provider({"TAVILY_API_KEY": ""}) == "duckduckgo"


class TestNormalize:
    STD = [{"title": "T", "url": "http://u", "snippet": "snip"}]

    def test_duckduckgo_shape(self):
        raw = [{"title": "T", "href": "http://u", "body": "snip"}]
        assert normalize_results("duckduckgo", raw) == self.STD

    def test_tavily_shape(self):
        raw = {"results": [{"title": "T", "url": "http://u", "content": "snip"}]}
        assert normalize_results("tavily", raw) == self.STD

    def test_brave_shape(self):
        raw = {"web": {"results": [{"title": "T", "url": "http://u", "description": "snip"}]}}
        assert normalize_results("brave", raw) == self.STD

    def test_handles_missing_fields(self):
        raw = [{"href": "http://u"}]
        out = normalize_results("duckduckgo", raw)
        assert out == [{"title": "", "url": "http://u", "snippet": ""}]

    def test_empty_results(self):
        assert normalize_results("tavily", {"results": []}) == []
        assert normalize_results("brave", {}) == []
