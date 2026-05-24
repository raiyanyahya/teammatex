import re
from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)

TECH_DEBT_PATTERNS = [
    (re.compile(r"TODO[:\s]*(.+)", re.IGNORECASE), "TODO"),
    (re.compile(r"FIXME[:\s]*(.+)", re.IGNORECASE), "FIXME"),
    (re.compile(r"HACK[:\s]*(.+)", re.IGNORECASE), "HACK"),
    (re.compile(r"XXX[:\s]*(.+)", re.IGNORECASE), "XXX"),
    (re.compile(r"WORKAROUND[:\s]*(.+)", re.IGNORECASE), "WORKAROUND"),
    (re.compile(r"BUG[:\s]*(.+)", re.IGNORECASE), "BUG"),
    (re.compile(r"OPTIMIZE[:\s]*(.+)", re.IGNORECASE), "OPTIMIZE"),
]

DEPRECATED_INDICATORS = [
    re.compile(r"@deprecated", re.IGNORECASE),
    re.compile(r"deprecated", re.IGNORECASE),
    re.compile(r"DeprecatedWarning"),
]

STALE_BRANCH_DAYS = 60


class TechDebtScanner:
    async def scan(self, repo_id: str, clone_path: str) -> list[dict]:
        items: list[dict] = []
        root = Path(clone_path)

        for file_path in root.rglob("*"):
            if not file_path.is_file() or ".git" in file_path.parts:
                continue

            fpath = str(file_path)
            rel_path = str(file_path.relative_to(root))

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                for pattern, tag_type in TECH_DEBT_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        description = match.group(1).strip()
                        severity = "high" if tag_type in ("FIXME", "BUG") else "medium"
                        items.append({
                            "repo_id": repo_id,
                            "file_path": rel_path,
                            "line_number": i,
                            "title": f"{tag_type}: {description[:100]}" if description else f"{tag_type}",
                            "type": tag_type,
                            "severity": severity,
                            "description": description[:500] if description else line.strip(),
                        })

                for pattern in DEPRECATED_INDICATORS:
                    if pattern.search(line):
                        items.append({
                            "repo_id": repo_id,
                            "file_path": rel_path,
                            "line_number": i,
                            "title": "Deprecated usage",
                            "type": "DEPRECATED",
                            "severity": "medium",
                            "description": line.strip()[:500],
                        })

        logger.info("tech_debt_scanned", repo_id=repo_id, items=len(items))
        return items
