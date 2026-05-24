from pathlib import Path
from typing import Optional

import structlog
import yaml

logger = structlog.get_logger(__name__)


class TeammateXDir:
    """Scans and loads .teammatex/ directory from a repository."""

    CONFIG_FILES = {
        "knowledge": "knowledge/",
        "conventions": "conventions.md",
        "owners": "owners.yaml",
        "ignore": "ignore",
        "personality": "personality.md",
    }

    def __init__(self, repo_path: str):
        self.root = Path(repo_path) / ".teammatex"

    def exists(self) -> bool:
        return self.root.exists()

    def load_knowledge(self) -> list[dict]:
        knowledge_dir = self.root / "knowledge"
        if not knowledge_dir.exists():
            return []
        docs: list[dict] = []
        for md_file in knowledge_dir.glob("*.md"):
            try:
                content = md_file.read_text(errors="replace")
                docs.append({
                    "title": md_file.stem.replace("_", " ").title(),
                    "content": content,
                    "source": str(md_file.relative_to(self.root.parent)),
                })
            except Exception as e:
                logger.warning("knowledge_read_error", file=str(md_file), error=str(e))
        return docs

    def load_conventions(self) -> str | None:
        path = self.root / "conventions.md"
        if not path.exists():
            return None
        return path.read_text(errors="replace")

    def load_owners(self) -> dict:
        path = self.root / "owners.yaml"
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text()) or {}
        except Exception as e:
            logger.warning("owners_parse_error", error=str(e))
            return {}

    def load_ignore_patterns(self) -> list[str]:
        path = self.root / "ignore"
        if not path.exists():
            return [".git/", "__pycache__/", "node_modules/", "*.pyc", ".venv/"]
        return [
            line.strip()
            for line in path.read_text(errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def load_personality_override(self) -> str | None:
        path = self.root / "personality.md"
        if not path.exists():
            return None
        return path.read_text(errors="replace")

    def load_all(self) -> dict:
        return {
            "knowledge": self.load_knowledge(),
            "conventions": self.load_conventions(),
            "owners": self.load_owners(),
            "ignore_patterns": self.load_ignore_patterns(),
            "personality_override": self.load_personality_override(),
        }
