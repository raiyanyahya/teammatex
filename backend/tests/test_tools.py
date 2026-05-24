"""Test tool registry, tool definitions, and path safety."""

import pytest

from app.services.agent.tools import ToolRegistry, ToolDefinition, tool_registry
from app.services.agent.runtime import _is_safe_path


class TestToolRegistry:
    def test_all_tools_registered(self):
        tools = tool_registry.get_all()
        assert len(tools) >= 20, f"Expected at least 20 tools, got {len(tools)}"

        expected_tools = [
            "read_file", "write_file", "edit_file", "list_directory",
            "glob_search", "grep_search", "semantic_search",
            "find_owner", "find_dependents", "find_dependencies",
            "get_architecture", "search_notes", "write_note",
            "create_branch", "commit_files", "create_pr",
            "get_diff", "get_blame", "get_commit_log",
            "run_command", "run_tests", "run_lint",
            "ask_question", "http_request", "schedule_task", "report_status",
        ]
        for tool_name in expected_tools:
            assert tool_name in tools, f"Missing tool: {tool_name}"

    def test_tool_definitions_have_required_fields(self):
        tools = tool_registry.get_all()
        for name, tool in tools.items():
            assert tool.name
            assert tool.description
            assert tool.parameters
            assert "type" in tool.parameters
            assert tool.category

    def test_file_tools_have_path_params(self):
        read_file = tool_registry.get("read_file")
        assert read_file is not None
        assert "file_path" in read_file.parameters.get("properties", {})

    def test_git_tools_have_safety_flags(self):
        create_pr = tool_registry.get("create_pr")
        assert create_pr is not None
        assert create_pr.requires_confirmation is True

    def test_knowledge_tools_no_confirmation(self):
        search = tool_registry.get("semantic_search")
        assert search is not None
        assert search.requires_confirmation is False

    def test_get_openai_tools_format(self):
        tools = tool_registry.get_openai_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "parameters" in tool["function"]

    def test_requires_confirmation_method(self):
        assert tool_registry.requires_confirmation("create_pr") is True
        assert tool_registry.requires_confirmation("read_file") is False
        assert tool_registry.requires_confirmation("nonexistent") is True

    def test_singleton_pattern(self):
        registry2 = ToolRegistry()
        assert registry2 is tool_registry
        assert len(registry2.get_all()) == len(tool_registry.get_all())


class TestPathSafety:
    def test_safe_path_inside_data_repos(self):
        assert _is_safe_path("/data/repos/my-repo/src/main.py") is True

    def test_safe_path_tmp(self):
        assert _is_safe_path("/tmp/test-file.py") is True

    def test_safe_path_app(self):
        assert _is_safe_path("/app/config.py") is True

    def test_unsafe_path_etc_passwd(self):
        assert _is_safe_path("/etc/passwd") is False

    def test_unsafe_path_home(self):
        assert _is_safe_path("/home/user/.ssh/id_rsa") is False

    def test_unsafe_path_root(self):
        assert _is_safe_path("/root/.bashrc") is False

    def test_path_traversal_blocked(self):
        assert _is_safe_path("/data/repos/../../../etc/passwd") is False

    def test_symlink_like_paths(self):
        assert _is_safe_path("/data/repos/..") is False


class TestCustomToolRegistration:
    def test_register_custom_tool(self):
        registry = ToolRegistry()
        initial_count = len(registry.get_all())

        custom_tool = ToolDefinition(
            name="test_custom_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}, "required": []},
            category="test",
        )
        registry.register(custom_tool)

        assert registry.get("test_custom_tool") is not None

    def test_overwrite_existing_tool(self):
        registry = ToolRegistry()
        count_before = len(registry.get_all())

        new_tool = ToolDefinition(
            name="read_file",
            description="Overwritten read_file",
            parameters={"type": "object", "properties": {}, "required": []},
            category="file",
        )
        registry.register(new_tool)

        tool = registry.get("read_file")
        assert tool is not None
        assert tool.description == "Overwritten read_file"
