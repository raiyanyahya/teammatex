import json
import re
from pathlib import Path
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)

SUPPORTED_PACKAGE_FILES = [
    "requirements.txt",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
]


class DependencyScanner:
    async def scan(self, repo_id: str, clone_path: str) -> dict:
        dependencies: dict[str, Any] = {
            "repo_id": repo_id,
            "packages": {},
        }

        root = Path(clone_path)
        for package_file in SUPPORTED_PACKAGE_FILES:
            matches = list(root.rglob(package_file))
            for match in matches:
                if ".git" in match.parts:
                    continue
                rel_path = str(match.relative_to(root))
                try:
                    parsed = self._parse_file(match)
                    if parsed:
                        dependencies["packages"][rel_path] = parsed
                except Exception as e:
                    logger.debug("dependency_parse_failed", file=rel_path, error=str(e))

        return dependencies

    def _parse_file(self, file_path: Path) -> Any:
        name = file_path.name.lower()

        if name == "requirements.txt":
            return self._parse_requirements(file_path)
        elif name == "package.json":
            return self._parse_package_json(file_path)
        elif name == "go.mod":
            return self._parse_go_mod(file_path)
        elif name == "cargo.toml":
            return self._parse_cargo_toml(file_path)
        elif name == "pom.xml":
            return self._parse_pom_xml(file_path)

        return None

    def _parse_requirements(self, path: Path) -> list[dict]:
        deps = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    parts = re.split(r"[=<>~!]", line, maxsplit=1)
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else "latest"
                    deps.append({"name": name, "version": version, "type": "pypi"})
        return deps

    def _parse_package_json(self, path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        deps = {}
        for section in ["dependencies", "devDependencies"]:
            for name, version in (data.get(section) or {}).items():
                deps[name] = {"version": version, "type": "npm", "dev": section == "devDependencies"}
        return deps

    def _parse_go_mod(self, path: Path) -> list[dict]:
        deps = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            in_require = False
            for line in f:
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                elif in_require and line == ")":
                    in_require = False
                elif in_require and line:
                    parts = line.split()
                    if len(parts) >= 2:
                        deps.append({"name": parts[0], "version": parts[1], "type": "go"})
        return deps

    def _parse_cargo_toml(self, path: Path) -> list[dict]:
        deps = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            in_deps = False
            for line in f:
                line = line.strip()
                if line == "[dependencies]" or line.startswith("[dependencies."):
                    in_deps = True
                elif line.startswith("[") and in_deps:
                    in_deps = False
                elif in_deps and "=" in line:
                    parts = line.split("=", 1)
                    name = parts[0].strip().strip('"')
                    version = parts[1].strip().strip('"')
                    deps.append({"name": name, "version": version, "type": "cargo"})
        return deps

    def _parse_pom_xml(self, path: Path) -> list[dict]:
        deps = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            group_matches = re.findall(r"<groupId>([^<]+)</groupId>", content)
            artifact_matches = re.findall(r"<artifactId>([^<]+)</artifactId>", content)
            version_matches = re.findall(r"<version>([^<]+)</version>", content)
            for g, a, v in zip(group_matches, artifact_matches, version_matches):
                deps.append({"name": f"{g}:{a}", "version": v, "type": "maven"})
        return deps[:50]  # limit
