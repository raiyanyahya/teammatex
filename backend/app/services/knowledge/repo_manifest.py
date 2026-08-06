import hashlib
from pathlib import Path
from typing import Any


class RepoManifest:
    def __init__(self, clone_path: str):
        self.clone_path = clone_path
        self._files: dict[str, str] = {}
        self._mtime: dict[str, float] = {}
        self._size: dict[str, int] = {}

    def scan(self) -> dict[str, dict[str, Any]]:
        root = Path(self.clone_path)
        manifest: dict[str, dict[str, Any]] = {}
        for fp in root.rglob("*"):
            if (
                not fp.is_file()
                or ".git" in fp.parts
                or "node_modules" in fp.parts
                or fp.stat().st_size > 10_000_000
            ):
                continue
            rel = str(fp.relative_to(root))
            try:
                content = fp.read_bytes()
                sha = hashlib.sha256(content).hexdigest()[:32]
                mtime = fp.stat().st_mtime
                size = len(content)
                manifest[rel] = {"sha256": sha, "mtime": mtime, "size": size}
                self._files[rel] = sha
                self._mtime[rel] = mtime
                self._size[rel] = size
            except Exception:
                pass
        return manifest

    def diff(self, previous: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        current = self.scan()
        changed: list[str] = []
        added: list[str] = []
        removed: list[str] = []

        for path, info in current.items():
            if path not in previous:
                added.append(path)
            elif previous[path]["sha256"] != info["sha256"]:
                changed.append(path)

        for path in previous:
            if path not in current:
                removed.append(path)

        return {"added": added, "changed": changed, "removed": removed}

    @staticmethod
    def classify_path_role(rel_path: str) -> str:
        lower = rel_path.lower()
        test_patterns = [
            "test/",
            "tests/",
            "_test.",
            "_spec.",
            ".test.",
            ".spec.",
            "conftest.py",
            "setup.py",
            "mock",
            "stub",
        ]
        fixture_patterns = [
            "fixture",
            "mock",
            "stub",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".env",
        ]
        generated_patterns = [
            "__generated__",
            ".gen.",
            ".generated.",
            "node_modules/",
            "__pycache__/",
            ".pyc",
            "dist/",
            "build/",
            ".egg-info/",
            "vendor/",
            "target/",
            "Cargo.lock",
            "poetry.lock",
            "package-lock.json",
            "yarn.lock",
            ".min.",
            ".bundle.",
        ]
        config_patterns = ["config", "settings", ".env", ".ini", ".cfg", ".toml", ".yaml", ".yml"]

        for p in generated_patterns:
            if p in lower:
                return "generated"
        for p in fixture_patterns:
            if p in lower and "test" not in lower and "spec" not in lower:
                return "fixture"
        for p in test_patterns:
            if p in lower:
                return "test"
        for p in config_patterns:
            if p in lower:
                return "config"
        return "production"
