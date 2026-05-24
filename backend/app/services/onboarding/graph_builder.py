from pathlib import Path

from structlog import get_logger

from app.services.knowledge.graph import KnowledgeGraph
from app.services.onboarding.code_parser import CodeParser
from app.services.onboarding.people_profiler import PeopleProfiler

logger = get_logger(__name__)


class GraphBuilder:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()
        self.parser = CodeParser()
        self.profiler = PeopleProfiler()

    async def build(self, repo_id: str, repo_name: str, clone_path: str) -> dict:
        await self.graph.ensure_repo_node(repo_id, repo_name)

        files_processed = 0
        entities_found = 0
        relationships_created = 0
        errors: list[str] = []

        root = Path(clone_path)
        for file_path in root.rglob("*"):
            if not file_path.is_file() or ".git" in file_path.parts:
                continue
            rel_path = str(file_path.relative_to(root))
            fpath = str(file_path)

            analysis = self.parser.parse_file(fpath)
            if not analysis:
                continue

            files_processed += 1
            lang = analysis.language

            await self.graph.ensure_file_node(repo_id, rel_path, lang, analysis.lines)

            # Module detection from first path component
            parts = Path(rel_path).parts
            if len(parts) > 1:
                await self.graph.ensure_module_node(repo_id, parts[0])

            for entity in analysis.entities:
                entities_found += 1
                if entity.kind == "function":
                    await self.graph.ensure_function_node(
                        repo_id, rel_path, entity.name,
                        entity.start_line, entity.end_line,
                        lang, entity.signature,
                    )
                elif entity.kind == "class":
                    await self.graph.ensure_class_node(
                        repo_id, rel_path, entity.name,
                        entity.start_line, entity.end_line, lang,
                    )

            for dep in analysis.dependencies:
                if dep.kind == "imports":
                    if dep.target:
                        for mod_name in dep.target.replace("import ", "").replace("from ", "").split(","):
                            clean = mod_name.strip().strip("\"'").split()[0].lstrip(".")
                            if clean and not clean.startswith("."):
                                try:
                                    await self.graph.ensure_module_node(repo_id, clean)
                                    relationships_created += 1
                                except Exception:
                                    pass
                elif dep.kind == "calls":
                    if dep.target:
                        for entity in analysis.entities:
                            if entity.kind == "function" and dep.source:
                                try:
                                    await self.graph.add_call_relationship(
                                        repo_id, rel_path, entity.name, entity.start_line, dep.target,
                                    )
                                    relationships_created += 1
                                except Exception:
                                    pass

        # Build contributor graph
        profiles = self.profiler.profile_repo(clone_path)
        for email, profile in profiles.items():
            await self.graph.ensure_contributor_node(email, profile.name)
            for owned_file in profile.owned_files:
                try:
                    await self.graph.add_ownership(
                        email, repo_id, owned_file, weight=1.0,
                    )
                    relationships_created += 1
                except Exception:
                    pass

        logger.info(
            "graph_built",
            repo=repo_name,
            files=files_processed,
            entities=entities_found,
            relationships=relationships_created,
            contributors=len(profiles),
        )

        return {
            "files_processed": files_processed,
            "entities_found": entities_found,
            "relationships_created": relationships_created,
            "contributors": len(profiles),
        }
