"""Turn an agent turn's tool activity into a deduped, ordered list of the source
files it consulted — the data behind the chat answer's 'Sources' list and the
eval harness's notion of what was retrieved.

Pure: input is a list of {"tool", "args", "result"} dicts (result is the
execute_tool envelope {"success": True, "data": ...}); output is Source dicts.
No DB, no LLM.
"""

from __future__ import annotations

# Tools whose `file_path` argument names a specific source file.
_FILE_ARG_TOOLS = {"read_file", "edit_file", "write_file", "get_blame", "find_owner"}


def _unwrap(result):
    if isinstance(result, dict) and result.get("success") and "data" in result:
        return result["data"]
    return None  # errors / unknown shapes contribute no sources


def extract_sources(invocations: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()

    def add(path, tool, lines=None):
        if not path or not isinstance(path, str) or path in seen:
            return
        seen.add(path)
        src = {"path": path, "tool": tool}
        if lines:
            src["lines"] = lines
        sources.append(src)

    for inv in invocations:
        tool = inv.get("tool")
        args = inv.get("args") or {}
        data = _unwrap(inv.get("result"))

        if data is None:
            continue

        if tool == "semantic_search" and isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("file_path"):
                    lines = None
                    if item.get("start_line") and item.get("end_line"):
                        lines = f"{item['start_line']}-{item['end_line']}"
                    add(item["file_path"], tool, lines)
        elif tool in _FILE_ARG_TOOLS:
            add(args.get("file_path") or args.get("path"), tool)

    return sources
