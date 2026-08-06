from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never be trusted as a JWT signing key: the code default, the
# placeholders shipped in .env.example, anything empty, and anything so short it
# is trivially brute-forced. All are publicly known, so a token signed with one
# can be forged by anyone. A key matching any of these is replaced at boot with a
# random per-process key (see below), which closes the forgery path by default.
_INSECURE_SECRET_KEYS = {
    "",
    "change-me",
    "change-me-to-a-random-string",
}


def _is_insecure_secret_key(key: str) -> bool:
    k = (key or "").strip()
    return k in _INSECURE_SECRET_KEYS or k.startswith("change-me") or len(k) < 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    teammate_name: str = "TeammateX"
    teammate_persona: str = "helpful_senior_dev"
    # The env convention is TEAMMATEX_* (see neo4j_uri). Without this alias the
    # field maps to TEAMMATE_SECRET_KEY (no X), never matches the configured
    # TEAMMATEX_SECRET_KEY, and the app silently signs every JWT with the public
    # default "change-me" — which would let anyone forge a token past the gate.
    teammate_secret_key: str = Field(default="change-me", validation_alias="TEAMMATEX_SECRET_KEY")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "teammatex"
    postgres_user: str = "teammatex"
    postgres_password: str = "teammatex"

    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="TEAMMATEX_NEO4J_URI")
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    deepseek_api_key: str = ""
    # Cheap default. deepseek-chat is deprecated (retires 2026-07-24); v4-flash is
    # the current non-thinking model and the right choice for tool loops.
    deepseek_model: str = "deepseek-v4-flash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-70b-versatile"

    # Local embeddings run on fastembed (ONNX, no torch). bge-small-en-v1.5 is
    # 384-dim and outscored all-MiniLM-L6-v2 on a retrieval bake-off of this repo.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""

    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""

    auto_sync_webhook_enabled: bool = False
    auto_sync_poll_interval_minutes: int = 15
    auto_sync_max_concurrent: int = 2

    digest_enabled: bool = True
    digest_schedule_day: str = "monday"
    digest_schedule_hour: int = 9

    prometheus_enabled: bool = True
    grafana_admin_password: str = "admin"

    # Set COOKIE_SECURE=true in production (behind HTTPS) so the session cookie
    # carries the Secure flag and is never sent over plain http. Left False by
    # default so local http://localhost development still works.
    cookie_secure: bool = False

    # /metrics is exposed only when this token is set, and then only to callers
    # presenting it (Bearer or ?token=). Empty (default) → the endpoint is not
    # mounted at all, so metrics are never world-readable by default. Set the
    # same value in docker/prometheus.yml's authorization block to scrape.
    metrics_token: str = Field(default="", validation_alias="TEAMMATEX_METRICS_TOKEN")

    def validate_secret_key(self) -> None:
        # Check the flag captured at import, before the key was swapped: by the
        # time this runs the insecure key has already been replaced with a random
        # one, so re-checking self.teammate_secret_key would always look fine.
        if _SECRET_KEY_WAS_INSECURE:
            import warnings

            warnings.warn(
                "TEAMMATEX_SECRET_KEY is insecure (unset, a shipped placeholder, or too "
                "short). A random per-boot key is being used so tokens can't be forged with "
                "the public default, but sessions reset on every restart. Set a strong, "
                "persistent TEAMMATEX_SECRET_KEY for production.",
                RuntimeWarning,
            )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()

# Fail safe, not silent: if the signing key is unset or a public placeholder,
# swap in a strong random key generated fresh for this process. This makes a
# default `cp .env.example .env` deploy immune to token forgery out of the box
# (the old behaviour trusted the public default and let anyone mint a valid
# token). The trade-off is that sessions do not survive a restart until a real
# TEAMMATEX_SECRET_KEY is set; validate_secret_key() warns loudly at startup.
_SECRET_KEY_WAS_INSECURE = _is_insecure_secret_key(settings.teammate_secret_key)
if _SECRET_KEY_WAS_INSECURE:
    import secrets

    settings.teammate_secret_key = secrets.token_urlsafe(48)
