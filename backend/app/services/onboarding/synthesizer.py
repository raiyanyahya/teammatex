from structlog import get_logger

logger = get_logger(__name__)


class Synthesizer:
    def synthesize(self, repo_info: dict) -> list[dict]:
        notes: list[dict] = []

        notes.append(
            {
                "title": f"Architecture Overview — {repo_info.get('name', 'Unknown')}",
                "content": self._generate_architecture_note(repo_info),
                "entity_type": "repo",
            }
        )

        if repo_info.get("contributor_count", 0) > 0:
            notes.append(
                {
                    "title": "Team Structure",
                    "content": f"This repository has {repo_info.get('contributor_count')} contributors "
                    f"across {repo_info.get('commit_count', 0)} commits.",
                    "entity_type": "contributor",
                }
            )

        return notes

    def _generate_architecture_note(self, info: dict) -> str:
        lines = [
            f"# {info.get('name', 'Repository')}",
            "",
            f"- **Default branch**: {info.get('default_branch', 'main')}",
            f"- **Total files**: {info.get('total_files', 'N/A')}",
            f"- **Total commits**: {info.get('commit_count', 'N/A')}",
            f"- **Contributors**: {info.get('contributor_count', 'N/A')}",
            "",
            "## Languages",
        ]
        for lang, count in sorted(
            (info.get("languages") or {}).items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"- **{lang}**: {count} files")

        lines.extend(
            [
                "",
                "## Branches",
                ", ".join(info.get("branches", [])[:20]),
            ]
        )

        return "\n".join(lines)
