from structlog import get_logger

from app.services.knowledge.graph import KnowledgeGraph

logger = get_logger(__name__)


class DocsGenerator:
    def __init__(self):
        self.graph = KnowledgeGraph()

    async def generate_repo_docs(self, repo_id: str, repo_name: str) -> dict:
        architecture = await self.graph.get_architecture(repo_id)
        module_graph = await self.graph.get_module_graph(repo_id)

        docs = {
            "repo": repo_name,
            "format": "markdown",
            "sections": [],
        }

        docs["sections"].append(
            {
                "title": "Architecture Overview",
                "content": self._format_architecture(architecture, repo_name),
            }
        )

        if module_graph.get("nodes"):
            docs["sections"].append(
                {
                    "title": "Module Graph",
                    "content": self._format_module_graph(module_graph, repo_name),
                }
            )

        return docs

    def _format_architecture(self, modules: list[dict], repo_name: str) -> str:
        if not modules:
            return f"# Architecture — {repo_name}\n\nNo modules found. Run onboarding to build the knowledge graph."

        lines = [f"# Architecture — {repo_name}", ""]
        lines.append("## Modules")
        lines.append("")
        lines.append("| Module | Files | Functions |")
        lines.append("|--------|-------|-----------|")
        for mod in modules[:20]:
            lines.append(
                f"| {mod.get('module', 'N/A')} | {mod.get('file_count', 0)} | {mod.get('function_count', 0)} |"
            )
        return "\n".join(lines)

    def _format_module_graph(self, module_graph: dict, repo_name: str) -> str:
        nodes = module_graph.get("nodes", [])
        edges = module_graph.get("edges", [])

        lines = [f"# Module Graph — {repo_name}", ""]
        lines.append(f"**Modules**: {len(nodes)} | **Connections**: {len(edges)}")
        lines.append("")

        if edges:
            lines.append("## Module Dependencies")
            lines.append("")
            for edge in edges[:15]:
                lines.append(
                    f"- `{edge.get('source')}` → `{edge.get('target')}` (weight: {edge.get('weight', 0)})"
                )

        return "\n".join(lines)

    async def generate_entity_docs(self, repo_id: str, entity_name: str) -> str:
        deps = await self.graph.find_dependencies(repo_id, entity_name)
        dependents = await self.graph.find_dependents(repo_id, entity_name)

        lines = [f"# `{entity_name}`", ""]

        if deps:
            lines.append(f"**Depends on** ({len(deps)}):")
            for d in deps[:10]:
                lines.append(f"- `{d.get('callee')}` in `{d.get('file', 'unknown')}`")
            lines.append("")

        if dependents:
            lines.append(f"**Used by** ({len(dependents)}):")
            for d in dependents[:10]:
                lines.append(f"- `{d.get('caller')}` in `{d.get('file', 'unknown')}`")
            lines.append("")

        return "\n".join(lines)


docs_generator = DocsGenerator()
