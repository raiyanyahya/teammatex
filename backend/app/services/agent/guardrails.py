import re
from enum import Enum

from structlog import get_logger

logger = get_logger(__name__)


class GuardResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class GuardrailCheck:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


class GuardrailRunner:
    SECRET_PATTERNS = [
        (
            re.compile(
                r"(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
                re.IGNORECASE,
            ),
            "critical",
        ),
        (
            re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
            "critical",
        ),
        (re.compile(r"(?:ghp_|github_pat_)[a-zA-Z0-9]{36,}", re.IGNORECASE), "critical"),
        (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE), "critical"),
        (re.compile(r"s3cr3t|sk-[a-zA-Z0-9]{32,}", re.IGNORECASE), "high"),
        (re.compile(r"(?:mongodb|postgres|mysql|redis)://[^@\s]+:[^@\s]+@", re.IGNORECASE), "high"),
    ]

    SQL_INJECTION_PATTERNS = [
        re.compile(r"f['\"].*%(?:s|d|r|\().*(?:SELECT|INSERT|UPDATE|DELETE|DROP)\b", re.IGNORECASE),
        # A SQL string with a %-format placeholder (either order), e.g.
        # f"SELECT ... '%s'" % user_id — classic string-interpolated query.
        re.compile(r"['\"].*\b(?:SELECT|INSERT|UPDATE|DELETE|DROP)\b.*%[sdr]", re.IGNORECASE),
        re.compile(r"\.format\(.*(?:SELECT|INSERT|UPDATE|DELETE|DROP)\b", re.IGNORECASE),
        re.compile(r"\+[\s]*[\"']\s*WHERE.*(?:SELECT|INSERT|UPDATE)\b", re.IGNORECASE),
    ]

    # Path fragments that mark infrastructure / deploy-sensitive changes.
    CRITICAL_PATH_HINTS = (
        "infra/",
        "terraform",
        ".tf",
        "migrations/",
        "alembic/",
        "dockerfile",
        ".github/",
        "deploy",
        "secrets",
    )

    DANGEROUS_PATTERNS = [
        re.compile(r"os\.system\(|subprocess\.call\(.*shell\s*=\s*True", re.IGNORECASE),
        re.compile(r"eval\(|exec\(", re.IGNORECASE),
        re.compile(r"pickle\.loads?\(|yaml\.load\(", re.IGNORECASE),
        re.compile(r"__import__\(.*input|request\.|params\.", re.IGNORECASE),
    ]

    def check_secrets(self, code: str) -> list[dict]:
        findings: list[dict] = []
        for pattern, severity in self.SECRET_PATTERNS:
            for match in pattern.finditer(code):
                findings.append(
                    {
                        "type": "secret",
                        "severity": severity,
                        "match": (
                            match.group()[:60] + "..." if len(match.group()) > 60 else match.group()
                        ),
                        "line": code[: match.start()].count("\n") + 1,
                    }
                )
        return findings

    def check_sql_injection(self, code: str) -> list[dict]:
        findings: list[dict] = []
        for pattern in self.SQL_INJECTION_PATTERNS:
            for match in pattern.finditer(code):
                findings.append(
                    {
                        "type": "sql_injection",
                        "severity": "high",
                        "match": match.group()[:100],
                        "line": code[: match.start()].count("\n") + 1,
                    }
                )
        return findings

    def check_dangerous_calls(self, code: str) -> list[dict]:
        findings: list[dict] = []
        for pattern in self.DANGEROUS_PATTERNS:
            for match in pattern.finditer(code):
                findings.append(
                    {
                        "type": "dangerous_call",
                        "severity": "high",
                        "match": match.group()[:100],
                        "line": code[: match.start()].count("\n") + 1,
                    }
                )
        return findings

    def run_all_checks(self, code: str, file_path: str = "") -> GuardResult:
        findings = []
        findings.extend(self.check_secrets(code))
        findings.extend(self.check_sql_injection(code))
        findings.extend(self.check_dangerous_calls(code))

        if not findings:
            logger.debug("guardrail_pass", file=file_path)
            return GuardResult.PASS

        critical = [f for f in findings if f["severity"] == "critical"]
        high = [f for f in findings if f["severity"] == "high"]

        if critical:
            logger.warning(
                "guardrail_block",
                file=file_path,
                critical=len(critical),
                findings=[f["type"] for f in critical],
            )
            return GuardResult.BLOCK

        if high:
            logger.warning(
                "guardrail_warn",
                file=file_path,
                high=len(high),
                findings=[f["type"] for f in high],
            )
            return GuardResult.WARN

        return GuardResult.PASS

    def check_pr_policy(
        self,
        repo_name: str,
        branch: str,
        files_changed: list[str],
        is_deploy_freeze: bool = False,
    ) -> tuple[GuardResult, str]:
        if is_deploy_freeze:
            return GuardResult.BLOCK, "Deploy freeze in effect — no merges permitted."
        if not branch.startswith("teammatex/"):
            return (
                GuardResult.WARN,
                f"Branch '{branch}' does not follow the 'teammatex/' convention.",
            )
        if len(files_changed) > 50:
            return (GuardResult.WARN, f"Large PR: {len(files_changed)} files. Consider splitting.")
        critical = [
            f for f in files_changed if any(h in f.lower() for h in self.CRITICAL_PATH_HINTS)
        ]
        if critical:
            return (
                GuardResult.WARN,
                f"Touches deploy-sensitive files ({', '.join(critical[:3])}); extra review needed.",
            )
        return GuardResult.PASS, "PR policy check passed."


guardrails = GuardrailRunner()
