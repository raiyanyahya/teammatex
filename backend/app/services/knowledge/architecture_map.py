from dataclasses import dataclass, field
from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class ArchitectureNode:
    path: str
    role: str  # entrypoint, hub, leaf, interface, config
    category: str  # api, service, model, util, middleware, cli, config
    imports_count: int = 0
    imported_by_count: int = 0
    centrality: float = 0.0


@dataclass
class ArchitectureMap:
    repo_id: str
    nodes: list[ArchitectureNode] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    hubs: list[str] = field(default_factory=list)
    key_interfaces: list[str] = field(default_factory=list)


class ArchitectureAnalyzer:
    ENTRYPOINT_PATTERNS = ["main.py", "main.go", "index.js", "index.ts", "server.py",
                          "app.py", "api.py", "routes", "router", "cmd/", "cmd.", "main."]

    HUB_PATTERNS = ["auth", "database", "db", "models", "schema", "types", "interfaces",
                   "config", "settings", "core", "utils", "helpers", "middleware"]

    CATEGORY_MAP = {
        "api": ["api", "routes", "router", "endpoint", "handler", "controller", "views", "rest"],
        "service": ["service", "provider", "client", "repository", "gateway", "adapter", "broker"],
        "model": ["model", "entity", "schema", "types", "interfaces", "dto", "domain"],
        "util": ["util", "helper", "lib", "common", "shared", "tool", "support", "internal"],
        "middleware": ["middleware", "guard", "interceptor", "filter", "pipeline", "hook"],
        "config": ["config", "settings", "options", "env", "parameter", "constant"],
        "cli": ["cli", "cmd", "command", "main", "bin", "script", "entry"],
    }

    def __init__(self, repo_id: str):
        self.repo_id = repo_id

    async def build(self, clone_path: str, files_data: list[dict]) -> ArchitectureMap:
        amap = ArchitectureMap(repo_id=self.repo_id)

        imports_map: dict[str, set[str]] = {}
        imported_by_map: dict[str, set[str]] = {}

        for fdata in files_data:
            file_path = fdata.get("path", "")
            role = fdata.get("role", "production")
            module_name = self._module_from_path(file_path)

            imports = fdata.get("imports", [])
            imports_map[file_path] = set()

            for imp in imports:
                target = self._resolve_import_target(imp, module_name, files_data)
                if target:
                    imports_map[file_path].add(target)
                    imported_by_map.setdefault(target, set()).add(file_path)

            category = self._classify_category(file_path)
            arch_role = self._classify_arch_role(file_path, imports_map.get(file_path, set()),
                                                  imported_by_map.get(file_path, set()))

            in_count = len(imported_by_map.get(file_path, set()))
            out_count = len(imports_map.get(file_path, set()))
            centrality = self._compute_centrality(file_path, files_data, imported_by_map)

            node = ArchitectureNode(
                path=file_path, role=arch_role, category=category,
                imports_count=out_count, imported_by_count=in_count,
                centrality=round(centrality, 4),
            )
            amap.nodes.append(node)

            if arch_role == "entrypoint":
                amap.entrypoints.append(file_path)
            elif arch_role == "hub":
                amap.hubs.append(file_path)
            elif arch_role == "interface":
                amap.key_interfaces.append(file_path)

        amap.nodes.sort(key=lambda n: n.centrality, reverse=True)
        return amap

    def _module_from_path(self, file_path: str) -> str:
        parts = file_path.replace("\\", "/").split("/")
        if len(parts) <= 1:
            return ""
        return parts[0]

    def _resolve_import_target(self, imp: str, current_module: str, files_data: list[dict]) -> str | None:
        imp = imp.replace("import ", "").replace("from ", "").strip().strip("\"' ")
        parts = imp.split()
        if not parts:
            return None
        name = parts[0].lstrip(".").replace(".", "/")
        if name.startswith(("http", "@")):
            return None

        for fdata in files_data:
            fpath = fdata.get("path", "")
            if name in fpath or fpath.endswith(f"{name}.py") or fpath.endswith(f"{name}.ts"):
                return fpath

        if current_module:
            guess = f"{current_module}/{name}.py"
            for fdata in files_data:
                if guess in fdata.get("path", ""):
                    return fdata["path"]

        return None

    def _classify_category(self, file_path: str) -> str:
        lower = file_path.lower()
        for cat, patterns in self.CATEGORY_MAP.items():
            for p in patterns:
                if p in lower:
                    return cat
        return "util"

    def _classify_arch_role(self, file_path: str, imports: set[str], imported_by: set[str]) -> str:
        lower = file_path.lower()
        for ep in self.ENTRYPOINT_PATTERNS:
            if ep in lower:
                return "entrypoint"

        in_count = len(imported_by)
        out_count = len(imports)
        if in_count >= 5 and out_count <= 3:
            return "hub"
        if in_count >= 3:
            return "interface"
        return "leaf"

    def _compute_centrality(self, file_path: str, files_data: list[dict],
                            imported_by_map: dict[str, set[str]]) -> float:
        in_degree = len(imported_by_map.get(file_path, set()))
        total_files = max(len(files_data), 1)
        return min(1.0, in_degree / max(total_files * 0.1, 1))

    def to_context_string(self) -> str:
        lines = ["## Architecture Map"]
        lines.append(f"Total files: {len(self.nodes)}")
        if self.entrypoints:
            lines.append(f"\n### Entrypoints ({len(self.entrypoints)})")
            for ep in self.entrypoints[:5]:
                lines.append(f"- `{ep}`")
        if self.hubs:
            lines.append(f"\n### Hub Files ({len(self.hubs)}) — imported by many")
            for hub in self.hubs[:5]:
                lines.append(f"- `{hub}`")
        if self.key_interfaces:
            lines.append(f"\n### Key Interfaces ({len(self.key_interfaces)})")
            for ki in self.key_interfaces[:5]:
                lines.append(f"- `{ki}`")

        lines.append("\n### Top Files by Centrality")
        for node in self.nodes[:10]:
            lines.append(f"- `{node.path}` [role={node.role}] "
                        f"imported_by={node.imported_by_count} "
                        f"centrality={node.centrality:.3f}")
        return "\n".join(lines)
