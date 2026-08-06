from dataclasses import dataclass, field
from enum import Enum

from structlog import get_logger

from app.services.plugins.manifest import PluginManifest, discover_plugins

logger = get_logger(__name__)


class PluginStatus(str, Enum):
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    REGISTERED = "registered"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginInstance:
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.DISCOVERED
    error_message: str | None = None
    provided_tools: list[str] = field(default_factory=list)
    provided_providers: list[str] = field(default_factory=list)


class PluginRegistry:
    _instance: "PluginRegistry | None" = None
    _plugins: dict[str, PluginInstance] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, manifest: PluginManifest) -> PluginInstance:
        instance = PluginInstance(manifest=manifest)
        instance.provided_tools = manifest.get_tool_names()
        instance.provided_providers = manifest.get_provider_types()

        self._plugins[manifest.name] = instance
        logger.info("plugin_registered", name=manifest.name, version=manifest.version)
        return instance

    def get(self, name: str) -> PluginInstance | None:
        return self._plugins.get(name)

    def get_all(self) -> dict[str, PluginInstance]:
        return dict(self._plugins)

    def get_tools(self) -> dict[str, "PluginInstance"]:
        tools: dict[str, PluginInstance] = {}
        for name, inst in self._plugins.items():
            if inst.status == PluginStatus.ACTIVE:
                for tool in inst.provided_tools:
                    tools[tool] = inst
        return tools


class PluginManager:
    PLUGIN_DIRS = ["plugins", "/app/plugins", "~/.teammatex/plugins"]

    def __init__(self):
        self.registry = PluginRegistry()

    def discover_all(self) -> list[PluginManifest]:
        manifests: list[PluginManifest] = []
        for d in self.PLUGIN_DIRS:
            manifests.extend(discover_plugins(d))
        return manifests

    def load_all(self) -> dict[str, PluginInstance]:
        manifests = self.discover_all()
        results: dict[str, PluginInstance] = {}
        for manifest in manifests:
            instance = self.load_plugin(manifest)
            results[manifest.name] = instance
        return results

    def load_plugin(self, manifest: PluginManifest) -> PluginInstance:
        instance = self.registry.register(manifest)
        instance.status = PluginStatus.VALIDATED

        deps_ok = self._check_dependencies(manifest)
        if not deps_ok:
            instance.status = PluginStatus.ERROR
            instance.error_message = "Dependency check failed"
            return instance

        instance.status = PluginStatus.REGISTERED

        try:
            self._initialize_plugin(instance)
            instance.status = PluginStatus.ACTIVE
            logger.info("plugin_activated", name=manifest.name)
        except Exception as e:
            instance.status = PluginStatus.ERROR
            instance.error_message = str(e)[:500]
            logger.error("plugin_activation_failed", name=manifest.name, error=str(e))

        return instance

    def unload_plugin(self, name: str) -> bool:
        instance = self.registry.get(name)
        if not instance:
            return False

        try:
            self._shutdown_plugin(instance)
        except Exception as e:
            logger.warning("plugin_shutdown_error", name=name, error=str(e))

        instance.status = PluginStatus.DISABLED
        return True

    def reload_plugin(self, name: str) -> PluginInstance | None:
        if not self.unload_plugin(name):
            return None
        instance = self.registry.get(name)
        if instance:
            return self.load_plugin(instance.manifest)
        return None

    def _check_dependencies(self, manifest: PluginManifest) -> bool:
        if not manifest.dependencies:
            return True
        for dep in manifest.dependencies:
            try:
                importlib = __import__("importlib")
                importlib.import_module(dep.split(">=")[0].split("==")[0].split("~=")[0].strip())
            except ImportError:
                logger.warning("plugin_missing_dependency", name=manifest.name, dep=dep)
                return False
        return True

    def _initialize_plugin(self, instance: PluginInstance):
        for ep in instance.manifest.extension_points:
            if ep.startswith("tool:"):
                tool_name = ep.split(":", 1)[1] if ":" in ep else ""
                if tool_name not in instance.provided_tools:
                    instance.provided_tools.append(tool_name)

    def _shutdown_plugin(self, instance: PluginInstance):
        for tool_name in instance.provided_tools:
            try:
                if tool_name in self.registry._plugins:
                    del self.registry._plugins[tool_name]
            except Exception:
                pass
        try:
            import importlib

            mod = importlib.import_module(instance.manifest.name)
            if hasattr(mod, "shutdown"):
                mod.shutdown()
        except Exception:
            pass


plugin_manager = PluginManager()
