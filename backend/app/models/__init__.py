from app.models.api_registry import APIRegistryEntry
from app.models.app_config import AppConfig
from app.models.audit import AuditLog, CostLog, Feedback
from app.models.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.blocked import BlockedTask
from app.models.concept import Concept
from app.models.conversation import Conversation, Message
from app.models.dependency import DependencySnapshot
from app.models.integration import Integration
from app.models.note import Note
from app.models.notepad import Notepad
from app.models.permission import Permission
from app.models.pr import PR
from app.models.repo import Repo, RepoOnboardingState
from app.models.task import Task
from app.models.tech_debt import TechDebtItem
from app.models.trust import TrustLevel, TrustMetrics
from app.models.upload import Upload
from app.models.user import User

try:
    from app.models.code_embedding import CodeEmbedding

    _has_code_embedding = True
except ImportError:
    CodeEmbedding = None  # type: ignore
    _has_code_embedding = False

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "utcnow",
    "User",
    "Repo",
    "RepoOnboardingState",
    "Task",
    "PR",
    "Conversation",
    "Message",
    "Note",
    "Concept",
    "Integration",
    "AuditLog",
    "Feedback",
    "CostLog",
    "TechDebtItem",
    "DependencySnapshot",
    "Permission",
    "TrustLevel",
    "TrustMetrics",
    "BlockedTask",
    "APIRegistryEntry",
    "AppConfig",
    "Upload",
    "Notepad",
]

if _has_code_embedding:
    __all__.append("CodeEmbedding")
