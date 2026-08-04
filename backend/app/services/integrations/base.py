from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RepoInfo:
    id: str
    name: str
    full_name: str
    url: str
    default_branch: str
    language: str | None = None
    private: bool = False


@dataclass
class PRInfo:
    number: int
    title: str
    body: str | None
    branch: str
    base: str
    state: str
    url: str
    author: str
    created_at: datetime | None = None


@dataclass
class IssueInfo:
    key: str
    title: str
    description: str | None
    status: str
    assignee: str | None
    priority: str | None
    sprint: str | None
    url: str


@dataclass
class BoardInfo:
    id: str
    name: str
    project: str


@dataclass
class SprintInfo:
    id: str
    name: str
    state: str  # active, future, closed
    start_date: str | None = None
    end_date: str | None = None


@dataclass
class ChannelInfo:
    id: str
    name: str
    is_private: bool = False


class SCMProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def list_repos(self) -> list[RepoInfo]: ...

    @abstractmethod
    async def get_repo(self, name: str) -> RepoInfo | None: ...

    @abstractmethod
    async def create_branch(self, repo: str, name: str, base: str = "main") -> str: ...

    @abstractmethod
    async def get_file(self, repo: str, path: str, ref: str = "main") -> str | None: ...

    @abstractmethod
    async def create_or_update_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> dict: ...

    @abstractmethod
    async def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> PRInfo: ...

    @abstractmethod
    async def get_pr(self, repo: str, number: int) -> PRInfo | None: ...

    @abstractmethod
    async def comment_on_pr(self, repo: str, number: int, body: str) -> None: ...

    @abstractmethod
    async def list_prs(self, repo: str, state: str = "open") -> list[PRInfo]: ...

    @abstractmethod
    async def get_pr_diff(self, repo: str, number: int) -> str: ...


class ProjectMgmtProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def list_projects(self) -> list[dict]: ...

    @abstractmethod
    async def list_boards(self, project_key: str) -> list[BoardInfo]: ...

    @abstractmethod
    async def list_issues(
        self, project_key: str, sprint_id: str | None = None
    ) -> list[IssueInfo]: ...

    @abstractmethod
    async def get_issue(self, key: str) -> IssueInfo | None: ...

    @abstractmethod
    async def update_issue(self, key: str, fields: dict) -> None: ...

    @abstractmethod
    async def comment_on_issue(self, key: str, body: str) -> None: ...

    @abstractmethod
    async def list_sprints(self, board_id: str) -> list[SprintInfo]: ...

    @abstractmethod
    async def get_active_sprint(self, board_id: str) -> SprintInfo | None: ...

    @abstractmethod
    async def get_sprint_issues(self, sprint_id: str) -> list[IssueInfo]: ...


class ChatProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def send_message(self, channel: str, text: str, blocks: list | None = None) -> str: ...

    @abstractmethod
    async def send_dm(self, user_email: str, text: str) -> str: ...

    @abstractmethod
    async def list_channels(self) -> list[ChannelInfo]: ...

    @abstractmethod
    async def add_reaction(self, channel: str, timestamp: str, emoji: str) -> None: ...

    async def post_standup(self, channel: str, summary: dict) -> str:
        raise NotImplementedError

    async def post_pr_summary(self, channel: str, pr: dict) -> str:
        raise NotImplementedError

    async def post_notification(
        self, channel: str, title: str, message: str, level: str = "info"
    ) -> str:
        raise NotImplementedError


class IntegrationRegistry:
    _scm: SCMProvider | None = None
    _pm: ProjectMgmtProvider | None = None
    _chat: ChatProvider | None = None

    @classmethod
    def _close_provider(cls, provider):
        if not provider or not hasattr(provider, "close"):
            return
        import asyncio as _aio

        try:
            loop = _aio.get_running_loop()
            loop.create_task(provider.close())
        except RuntimeError:
            pass

    @classmethod
    def register_scm(cls, provider: SCMProvider):
        cls._close_provider(cls._scm)
        cls._scm = provider

    @classmethod
    def register_pm(cls, provider: ProjectMgmtProvider):
        cls._close_provider(cls._pm)
        cls._pm = provider

    @classmethod
    def register_chat(cls, provider: ChatProvider):
        cls._close_provider(cls._chat)
        cls._chat = provider

    @classmethod
    def get_scm(cls) -> SCMProvider | None:
        return cls._scm

    @classmethod
    def get_pm(cls) -> ProjectMgmtProvider | None:
        return cls._pm

    @classmethod
    def get_chat(cls) -> ChatProvider | None:
        return cls._chat
