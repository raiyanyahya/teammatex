from structlog import get_logger

from app.services.knowledge.embeddings import EmbeddingService
from app.services.knowledge.graph import KnowledgeGraph
from app.services.agent.confidence import compute_confidence, is_low_confidence, flag_if_low
from app.services.knowledge.incremental_graph import ImportCentrality

logger = get_logger(__name__)

QUERY_INTENTS = {
    "exact_name": ["find", "locate", "where is", "show me the", "what file", "which file contains"],
    "config": ["config", "settings", "env", "parameter", "option", "how to configure", "setup"],
    "wiring": ["depend", "import", "call", "connect", "what uses", "who uses", "reference", "where is X used", "what calls"],
    "flow": ["how does", "what happens when", "flow", "pipeline", "process", "workflow", "step by step", "trigger", "event"],
    "conceptual": ["what is", "explain", "architecture", "overview", "concept", "why", "design", "pattern", "strategy", "how should"],
}


def classify_query_intent(query: str) -> str:
    lower = query.lower()
    scores = {intent: 0 for intent in QUERY_INTENTS}
    for intent, keywords in QUERY_INTENTS.items():
        for kw in keywords:
            if kw in lower:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "conceptual"


def reciprocal_rank_fusion(result_sets: list[list[dict]], k: int = 60) -> list[dict]:
    fused: dict[str, dict] = {}
    for result_set in result_sets:
        for rank, item in enumerate(result_set):
            doc_id = item.get("file_path", item.get("id", str(rank)))
            if doc_id not in fused:
                fused[doc_id] = item.copy()
                fused[doc_id]["rrf_score"] = 0.0
            fused[doc_id]["rrf_score"] += 1.0 / (k + rank + 1)
    return sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)


class RAGPipeline:
    def __init__(self):
        self.embedder = EmbeddingService()
        self.graph = KnowledgeGraph()

    async def retrieve_context(
        self,
        db,
        query: str,
        repo_id: str | None = None,
        max_chunks: int = 5,
        max_graph_results: int = 3,
    ) -> str:
        intent = classify_query_intent(query)
        chunk_limit = max_chunks
        graph_limit = max_graph_results

        chunks = await self.embedder.search(db, query=query, repo_id=repo_id, limit=chunk_limit)
        graph_results = await self.graph.search_graph(query, limit=graph_limit)

        if repo_id:
            try:
                centrality = ImportCentrality(repo_id)
                chunks = await centrality.rank_files(chunks, repo_id)
            except Exception:
                pass

        context_parts: list[str] = []
        context_parts.append(f"[Query intent: {intent}]\n")

        if chunks:
            context_parts.append("## Code Search Results\n")
            for i, chunk in enumerate(chunks, 1):
                similarity = chunk.get("similarity", 0.5)
                confidence, tier = compute_confidence(similarity, category="search_result")
                flag = flag_if_low(confidence, f"result {i}")
                boost_note = f" [centrality_boost: +{chunk.get('centrality_boost', 0):.3f}]" if chunk.get("centrality_boost") else ""
                context_parts.append(
                    f"### Result {i}: {chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']} "
                    f"[confidence: {confidence:.2f} — {tier.value}{boost_note}]{' ' + flag if flag else ''}\n"
                    f"Entity: {chunk.get('entity_name', 'N/A')} ({chunk.get('entity_type', 'unknown')})\n"
                    f"```{chunk.get('language', '')}\n{chunk['text']}\n```\n"
                )

        if graph_results:
            context_parts.append("## Graph Search Results\n")
            for i, node in enumerate(graph_results, 1):
                node_type = node.get("type", "unknown")
                props = node.get("properties", {})
                name = props.get("name", props.get("path", props.get("title", "unnamed")))
                edge_confidence = props.get("weight", 0.7)
                confidence, tier = compute_confidence(edge_confidence, category="relationship")
                flag = flag_if_low(confidence, name)
                context_parts.append(
                    f"- [{node_type}] {name} [confidence: {confidence:.2f} — {tier.value}]"
                    f"{' ' + flag if flag else ''}"
                )
                if props.get("signature"):
                    context_parts.append(f"  Signature: {props['signature']}")
                if props.get("path"):
                    context_parts.append(f"  Path: {props['path']}")
                if props.get("role"):
                    context_parts.append(f"  Role: {props['role']}")
                context_parts.append("")

        if not context_parts:
            return "(No relevant context found in the codebase.)"

        return "\n".join(context_parts)

    async def build_context_for_task(
        self,
        db,
        task_description: str,
        repo_id: str | None = None,
        files_to_modify: list[str] | None = None,
    ) -> str:
        context = await self.retrieve_context(db, task_description, repo_id, max_chunks=8)

        if files_to_modify:
            context += "\n## Files to Modify\n"
            for f in files_to_modify:
                context += f"- `{f}`\n"
                try:
                    owner = await self.graph.find_owner(repo_id or "", f)
                    if owner:
                        context += f"  Owner: {owner.get('name')} ({owner.get('email')})\n"
                except Exception:
                    pass

        return context
