import hashlib

EXTRACTOR_VERSION = "1.0.0"


def node_id(repo_id: str, entity_type: str, path: str, name: str = "") -> str:
    raw = f"{repo_id}:{entity_type}:{path}:{name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def edge_id(repo_id: str, rel_type: str, from_node_id: str, to_node_id: str) -> str:
    raw = f"{repo_id}:{rel_type}:{from_node_id}:{to_node_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
