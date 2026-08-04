from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)


class LanguageAutoDiscovery:
    EXTENSION_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".cpp": "c++",
        ".c": "c",
        ".h": "c",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".cs": "csharp",
        ".php": "php",
        ".r": "r",
        ".jl": "julia",
        ".lua": "lua",
        ".proto": "protobuf",
        ".graphql": "graphql",
        ".sql": "sql",
        ".tf": "terraform",
        ".hcl": "terraform",
        ".dockerfile": "dockerfile",
        ".vue": "vue",
        ".svelte": "svelte",
        ".elm": "elm",
        ".dart": "dart",
    }

    def scan_unknown_languages(self, clone_path: str) -> list[dict]:
        unknown: dict[str, dict] = {}
        root = Path(clone_path)

        for file_path in root.rglob("*"):
            if not file_path.is_file() or ".git" in file_path.parts:
                continue

            ext = file_path.suffix.lower()
            if not ext:
                name_parts = file_path.name.lower()
                for keyword in ["dockerfile", "makefile", "jenkinsfile", "vagrantfile"]:
                    if keyword in name_parts:
                        ext = f".{keyword}"
                        break
                if not ext:
                    continue

            lang = self.EXTENSION_MAP.get(ext)
            if lang:
                continue  # Known language

            if ext not in unknown:
                unknown[ext] = {"extension": ext, "files": [], "count": 0}
            unknown[ext]["count"] += 1
            if len(unknown[ext]["files"]) < 5:
                unknown[ext]["files"].append(str(file_path.relative_to(root)))

        return sorted(unknown.values(), key=lambda x: x["count"], reverse=True)

    def suggest_grammar_install(self, extension: str, file_count: int) -> dict:
        grammar_map = {
            ".swift": "tree-sitter-swift",
            ".kt": "tree-sitter-kotlin",
            ".scala": None,
            ".cs": "tree-sitter-c-sharp",
            ".php": "tree-sitter-php",
            ".r": None,
            ".jl": None,
            ".lua": "tree-sitter-lua",
            ".proto": None,
            ".graphql": None,
            ".sql": "tree-sitter-sql",
            ".tf": None,
            ".vue": "tree-sitter-vue",
            ".svelte": None,
            ".elm": "tree-sitter-elm",
            ".dart": None,
        }

        package = grammar_map.get(extension)
        if package:
            return {
                "extension": extension,
                "file_count": file_count,
                "grammar_package": package,
                "can_auto_install": True,
                "suggestion": f"Found {file_count} {extension} files. Install tree-sitter grammar: `pip install {package}`",
            }
        else:
            return {
                "extension": extension,
                "file_count": file_count,
                "grammar_package": None,
                "can_auto_install": False,
                "suggestion": f"Found {file_count} {extension} files. No tree-sitter grammar available. Consider adding a custom parser plugin.",
            }


class ToolSuggestionEngine:
    TOOL_PATTERNS = {
        "feature_flags": {
            "indicators": ["feature-flags.yaml", "feature_flags", "launchdarkly", "unleash"],
            "tool_template": {
                "name": "check_feature_flag",
                "description": "Check if a feature flag is enabled",
                "parameters": {"flag_name": "string", "environment": "string"},
            },
        },
        "config_management": {
            "indicators": ["config/", ".env", "settings.py", "application.yml"],
            "tool_template": {
                "name": "read_config",
                "description": "Read a configuration value from the team's config system",
                "parameters": {"key": "string"},
            },
        },
        "deployment": {
            "indicators": ["deploy/", "k8s/", "terraform/", "helm/", "Dockerfile"],
            "tool_template": {
                "name": "check_deployment_status",
                "description": "Check deployment status for a service",
                "parameters": {"service": "string", "environment": "string"},
            },
        },
        "monitoring": {
            "indicators": ["datadog", "grafana/", "prometheus", "alertmanager"],
            "tool_template": {
                "name": "query_metrics",
                "description": "Query monitoring metrics for a service",
                "parameters": {"query": "string", "time_range": "string"},
            },
        },
    }

    def scan_for_tool_opportunities(self, clone_path: str) -> list[dict]:
        suggestions: list[dict] = []
        root = Path(clone_path)

        for tool_name, config in self.TOOL_PATTERNS.items():
            indicators_found = []
            for indicator in config["indicators"]:
                matches = list(root.rglob(indicator))
                for match in matches:
                    if ".git" not in match.parts:
                        indicators_found.append(str(match.relative_to(root)))

            if indicators_found:
                suggestions.append(
                    {
                        "tool_name": tool_name,
                        "indicators_found": indicators_found[:5],
                        "tool_template": config["tool_template"],
                        "estimated_calls_per_month": len(indicators_found) * 10,
                        "suggestion": (
                            f"I keep seeing {tool_name.replace('_', ' ')} patterns in your codebase. "
                            f"I could create a '{config['tool_template']['name']}' tool to automate this."
                        ),
                    }
                )

        return suggestions


class PatternDiscovery:
    def detect_duplication(self, clone_path: str) -> list[dict]:
        import hashlib
        from collections import defaultdict

        hashes: dict[str, list[str]] = defaultdict(list)
        root = Path(clone_path)

        for file_path in root.rglob("*.py"):
            if ".git" in file_path.parts:
                continue
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) < 100:
                    continue
                h = hashlib.md5(content[:500].encode()).hexdigest()
                hashes[h].append(str(file_path.relative_to(root)))
            except Exception:
                pass

        duplicates = []
        for h, files in hashes.items():
            if len(files) > 1:
                duplicates.append(
                    {
                        "files": files[:5],
                        "count": len(files),
                        "type": "code_duplication",
                        "suggestion": f"Found {len(files)} files with highly similar headers. Consider extracting shared code.",
                    }
                )

        return sorted(duplicates, key=lambda x: x["count"], reverse=True)[:10]

    def detect_inconsistent_patterns(self, clone_path: str) -> list[dict]:
        patterns: list[dict] = []
        root = Path(clone_path)

        # Check for mix of REST and GraphQL
        rest_count = len(list(root.rglob("*routes*.py"))) + len(list(root.rglob("*router*.py")))
        graphql_count = len(list(root.rglob("*schema*.graphql"))) + len(
            list(root.rglob("*graphql*"))
        )
        if rest_count > 0 and graphql_count > 0:
            patterns.append(
                {
                    "type": "mixed_api_styles",
                    "rest_files": rest_count,
                    "graphql_files": graphql_count,
                    "suggestion": "Both REST and GraphQL APIs detected. Consider standardizing on one approach.",
                }
            )

        # Check for multiple test frameworks
        frameworks = set()
        for f in root.rglob("*"):
            if ".git" in f.parts:
                continue
            for keyword in ["unittest", "pytest", "jest", "mocha", "junit"]:
                if keyword in f.name.lower():
                    frameworks.add(keyword)
        if len(frameworks) > 1:
            patterns.append(
                {
                    "type": "multiple_test_frameworks",
                    "frameworks": list(frameworks),
                    "suggestion": f"Multiple test frameworks detected: {', '.join(frameworks)}. Consider standardizing.",
                }
            )

        return patterns


class SelfExtension:
    def __init__(self):
        self.language_discovery = LanguageAutoDiscovery()
        self.tool_suggester = ToolSuggestionEngine()
        self.pattern_analyzer = PatternDiscovery()

    async def run_full_scan(self, clone_path: str) -> dict:
        unknown_langs = self.language_discovery.scan_unknown_languages(clone_path)
        tool_suggestions = self.tool_suggester.scan_for_tool_opportunities(clone_path)
        duplications = self.pattern_analyzer.detect_duplication(clone_path)
        inconsistencies = self.pattern_analyzer.detect_inconsistent_patterns(clone_path)

        grammar_suggestions = []
        for lang in unknown_langs:
            suggestion = self.language_discovery.suggest_grammar_install(
                lang["extension"], lang["count"]
            )
            grammar_suggestions.append(suggestion)

        return {
            "unknown_languages": unknown_langs,
            "grammar_suggestions": grammar_suggestions,
            "tool_suggestions": tool_suggestions,
            "duplications": duplications,
            "inconsistencies": inconsistencies,
            "total_suggestions": (
                len(grammar_suggestions)
                + len(tool_suggestions)
                + len(duplications)
                + len(inconsistencies)
            ),
        }
