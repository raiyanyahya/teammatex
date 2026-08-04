import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)


class ExtensionPoint(str, Enum):
    PROVIDER = "provider"
    TOOL = "tool"
    PARSER = "parser"
    LLM = "llm"
    WORKFLOW = "workflow"
    KNOWLEDGE = "knowledge"
    UI = "ui"
    EVENT = "event"
    GUARDRAIL = "guardrail"


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    license: str = "MIT"
    homepage: str = ""
    min_app_version: str = "0.1.0"
    python: str = ">=3.12"
    dependencies: list[str] = field(default_factory=list)
    extension_points: list[str] = field(default_factory=list)
    config_schema: dict = field(default_factory=dict)
    path: str = ""

    @classmethod
    def from_toml(cls, path: str) -> "PluginManifest":
        with open(path, "rb") as f:
            data = tomllib.load(f)

        plugin = data.get("plugin", {})
        ext = plugin.get("extension_points", {})
        config = plugin.get("config", {})

        extension_points = []
        if isinstance(ext, dict):
            for category, values in ext.items():
                if isinstance(values, list):
                    extension_points.extend(f"{category}:{v}" for v in values)
                else:
                    extension_points.append(category)

        return cls(
            name=plugin.get("name", "unknown"),
            version=plugin.get("version", "0.0.0"),
            description=plugin.get("description", ""),
            author=plugin.get("author", "unknown"),
            license=plugin.get("license", "MIT"),
            homepage=plugin.get("homepage", ""),
            min_app_version=plugin.get("requirements", {}).get("min_app_version", "0.1.0"),
            python=plugin.get("requirements", {}).get("python", ">=3.12"),
            dependencies=plugin.get("requirements", {}).get("dependencies", []),
            extension_points=extension_points,
            config_schema=config.get("schema", {}),
            path=path,
        )

    def validate(self) -> tuple[bool, str]:
        if not self.name or self.name == "unknown":
            return False, "Plugin name is required"
        if not self.version:
            return False, "Plugin version is required"
        if not self.extension_points:
            return False, "Plugin must register at least one extension point"
        return True, "Valid"

    def get_provider_types(self) -> list[str]:
        return [ep.split(":")[0] for ep in self.extension_points if ep.startswith("provider:")]

    def get_tool_names(self) -> list[str]:
        return [ep.split(":")[1] for ep in self.extension_points if ep.startswith("tool:")]


def discover_plugins(plugin_dir: str = "plugins") -> list[PluginManifest]:
    manifests: list[PluginManifest] = []
    root = Path(plugin_dir)
    if not root.exists():
        return manifests

    for toml_path in root.rglob("teammatex-plugin.toml"):
        try:
            manifest = PluginManifest.from_toml(str(toml_path))
            manifest.path = str(toml_path.parent)
            valid, msg = manifest.validate()
            if valid:
                manifests.append(manifest)
                logger.info("plugin_discovered", name=manifest.name, version=manifest.version)
            else:
                logger.warning("plugin_invalid", path=str(toml_path), reason=msg)
        except Exception as e:
            logger.error("plugin_manifest_error", path=str(toml_path), error=str(e))

    return manifests
