from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[dict]] | None = None
    requires_confirmation: bool = False
    category: str = "general"


class ToolRegistry:
    _instance: "ToolRegistry | None" = None
    _tools: dict[str, ToolDefinition] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._register_all()
        return cls._instance

    def _register_all(self):
        self._register_file_tools()
        self._register_git_tools()
        self._register_knowledge_tools()
        self._register_agent_tools()

    def _register_file_tools(self):
        self.register(ToolDefinition(
            name="read_file",
            description="Read the contents of a file. Returns the file content with line numbers.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to read"},
                    "start_line": {"type": "integer", "description": "Optional start line (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Optional end line (1-indexed)"},
                },
                "required": ["file_path"],
            },
            category="file",
        ))

        self.register(ToolDefinition(
            name="write_file",
            description="Write content to a file. Creates the file if it doesn't exist.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["file_path", "content"],
            },
            requires_confirmation=True,
            category="file",
        ))

        self.register(ToolDefinition(
            name="edit_file",
            description="Make a precise string replacement in an existing file.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to edit"},
                    "old_string": {"type": "string", "description": "Exact text to replace"},
                    "new_string": {"type": "string", "description": "Text to replace it with"},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
            requires_confirmation=True,
            category="file",
        ))

        self.register(ToolDefinition(
            name="list_directory",
            description="List files and directories in a given path. Use --limit to bound results. Use --kind to filter by file extension.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"},
                    "limit": {"type": "integer", "description": "Max entries to return (default: 50)", "default": 50},
                    "kind": {"type": "string", "description": "Filter by extension (e.g., '.py', '.ts') or type ('file', 'directory')"},
                },
                "required": ["path"],
            },
            category="file",
        ))

        self.register(ToolDefinition(
            name="glob_search",
            description="Search for files matching a glob pattern. Use --limit to bound results.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"},
                    "path": {"type": "string", "description": "Base directory to search from"},
                    "limit": {"type": "integer", "description": "Max results (default: 100)", "default": 100},
                },
                "required": ["pattern"],
            },
            category="file",
        ))

        self.register(ToolDefinition(
            name="grep_search",
            description="Search file contents for a regex pattern. Use --limit to bound results, --path to scope, --kind to filter by file type.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory to limit search scope"},
                    "include": {"type": "string", "description": "File pattern filter (e.g., '*.py', '*.ts')"},
                    "limit": {"type": "integer", "description": "Max matches to return (default: 50)", "default": 50},
                    "kind": {"type": "string", "description": "Only search files of this kind (e.g., 'python', 'typescript')"},
                },
                "required": ["pattern"],
            },
            category="file",
        ))

    def _register_git_tools(self):
        self.register(ToolDefinition(
            name="create_branch",
            description="Create a new git branch prefixed with teammatex/.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name (teammatex/ prefix added automatically)"},
                    "base": {"type": "string", "description": "Base branch (default: main)", "default": "main"},
                },
                "required": ["name"],
            },
            category="git",
        ))

        self.register(ToolDefinition(
            name="commit_files",
            description="Commit files to the current branch with a message.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "files": {
                        "type": "object",
                        "description": "Dict of file_path → content",
                    },
                },
                "required": ["message", "files"],
            },
            requires_confirmation=True,
            category="git",
        ))

        self.register(ToolDefinition(
            name="create_pr",
            description="Create a pull request from the current branch.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title"},
                    "body": {"type": "string", "description": "PR description (markdown)"},
                    "base": {"type": "string", "description": "Base branch", "default": "main"},
                },
                "required": ["title", "body"],
            },
            requires_confirmation=True,
            category="git",
        ))

        self.register(ToolDefinition(
            name="get_diff",
            description="Get the git diff between two refs or for the working tree.",
            parameters={
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "Base ref (default: HEAD~1)"},
                    "head": {"type": "string", "description": "Head ref (default: HEAD)"},
                    "path": {"type": "string", "description": "Optional file path filter"},
                },
                "required": [],
            },
            category="git",
        ))

        self.register(ToolDefinition(
            name="get_blame",
            description="Get git blame information for a file or specific lines.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["file_path"],
            },
            category="git",
        ))

        self.register(ToolDefinition(
            name="get_commit_log",
            description="Get recent commit history for a file or repo.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Optional: filter by file"},
                    "author": {"type": "string", "description": "Optional: filter by author email"},
                    "limit": {"type": "integer", "description": "Max commits (default: 20)", "default": 20},
                },
                "required": [],
            },
            category="git",
        ))

    def _register_knowledge_tools(self):
        self.register(ToolDefinition(
            name="semantic_search",
            description="Search the codebase semantically for code related to a query. Returns relevant code chunks.",
            parameters={...},
            category="knowledge",
        ))
        # ... existing tools ...

        self.register(ToolDefinition(
            name="web_search",
            description="Search the web for information. Returns search results.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="semantic_search",
            description="Search the codebase semantically for code related to a query. Use --limit to bound results, --kind to filter by entity type, --path to scope results.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query about the codebase"},
                    "repo_id": {"type": "string", "description": "Optional: filter by repo"},
                    "kind": {"type": "string", "description": "Entity type filter: function, class, module, file"},
                    "language": {"type": "string", "description": "Programming language filter"},
                    "path": {"type": "string", "description": "Scope search to files matching this path pattern"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
                },
                "required": ["query"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="graph_query",
            description="Search the knowledge graph directly by entity name, type, or relationship. Use --kind to filter by node type.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term (entity name, file path, or concept)"},
                    "kind": {"type": "string", "description": "Node type filter: Function, Class, Module, File, Feature, Repository"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
                },
                "required": ["query"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="find_owner",
            description="Find the primary contributor/owner of a file based on git history.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "Repository ID"},
                    "file_path": {"type": "string", "description": "File path within the repo"},
                },
                "required": ["repo_id", "file_path"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="find_dependents",
            description="Find all functions that call a given function.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                    "entity_name": {"type": "string", "description": "Function name to find callers of"},
                },
                "required": ["repo_id", "entity_name"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="find_dependencies",
            description="Find all functions called by a given function.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                    "entity_name": {"type": "string", "description": "Function name to find callees of"},
                },
                "required": ["repo_id", "entity_name"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="get_architecture",
            description="Get the module architecture overview for a repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                },
                "required": ["repo_id"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="search_notes",
            description="Search through the teammate's own notes and knowledge base.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 20},
                },
                "required": ["query"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="write_note",
            description="Write a note to the teammate's knowledge base.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Note content in markdown"},
                    "entity_type": {"type": "string", "description": "Type of related entity"},
                    "entity_id": {"type": "string", "description": "ID of related entity"},
                },
                "required": ["title", "content"],
            },
            category="knowledge",
        ))

    def _register_agent_tools(self):
        self.register(ToolDefinition(
            name="run_command",
            description="Run a shell command in a sandboxed environment.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "cwd": {"type": "string", "description": "Working directory"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                },
                "required": ["command"],
            },
            requires_confirmation=True,
            category="execution",
        ))

        self.register(ToolDefinition(
            name="run_tests",
            description="Run the test suite for a specific path or the entire project.",
            parameters={
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Optional: specific test file or directory"},
                },
                "required": [],
            },
            category="execution",
        ))

        self.register(ToolDefinition(
            name="run_lint",
            description="Run the linter on a specific file or directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory to lint"},
                },
                "required": ["path"],
            },
            category="execution",
        ))

        self.register(ToolDefinition(
            name="ask_question",
            description="Ask the team a question when uncertain. Blocks the current task until answered.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Current task ID"},
                    "question": {"type": "string", "description": "The question to ask the team"},
                    "context": {"type": "object", "description": "Additional context for the question"},
                },
                "required": ["task_id", "question"],
            },
            category="agent",
        ))

        self.register(ToolDefinition(
            name="http_request",
            description="Make an HTTP request to an approved external API.",
            parameters={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "url": {"type": "string", "description": "URL (must match approved API registry)"},
                    "headers": {"type": "object", "description": "Request headers"},
                    "body": {"type": "string", "description": "Request body (JSON string)"},
                },
                "required": ["method", "url"],
            },
            requires_confirmation=True,
            category="external",
        ))

        self.register(ToolDefinition(
            name="schedule_task",
            description="Schedule a recurring or future task.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Task name"},
                    "trigger_time": {"type": "string", "description": "ISO datetime or cron expression"},
                    "action": {"type": "object", "description": "Action to execute"},
                },
                "required": ["name", "trigger_time", "action"],
            },
            category="agent",
        ))

        self.register(ToolDefinition(
            name="report_status",
            description="Report the current status of the teammate's tasks and state.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            category="agent",
        ))

        self.register(ToolDefinition(
            name="explain_architecture",
            description="Generate an architecture overview and docs for the codebase. Explains how the system is structured.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "Repo ID to explain"},
                },
                "required": ["repo_id"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="trace_issue",
            description="Trace who broke a function or file using git blame and call graph. Finds likely culprits.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "Repo ID"},
                    "entity_name": {"type": "string", "description": "Function or entity name to trace"},
                    "file_path": {"type": "string", "description": "File path (optional)"},
                },
                "required": ["repo_id", "entity_name"],
            },
            category="knowledge",
        ))

        self.register(ToolDefinition(
            name="list_prs",
            description="List open pull requests for an onboarded repository. Requires GitHub integration.",
            parameters={
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Local name of the onboarded repo (e.g. 'kit-fork')"},
                    "state": {"type": "string", "description": "PR state filter: open, closed, all (default: open)"},
                    "limit": {"type": "integer", "description": "Max PRs to list (default: 10)", "default": 10},
                },
                "required": ["repo_name"],
            },
            category="integrations",
        ))

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_all(self) -> dict[str, ToolDefinition]:
        return dict(self._tools)

    def get_openai_tools(self) -> list[dict]:
        tools = []
        for name, td in self._tools.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            })
        return tools

    def requires_confirmation(self, tool_name: str) -> bool:
        tool = self._tools.get(tool_name)
        return tool.requires_confirmation if tool else True


tool_registry = ToolRegistry()
