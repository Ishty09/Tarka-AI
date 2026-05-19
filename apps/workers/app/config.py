"""Runtime configuration via pydantic-settings.

Loaded once at import time from the process environment (+ optional .env in
dev). Fields are typed and validated — a missing required key fails fast at
startup rather than producing confusing 500s later.
"""

from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker settings sourced from §5 environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- App ---------------------------------------------------------------
    node_env: str = Field(default="development", alias="NODE_ENV")
    app_url: HttpUrl = Field(alias="NEXT_PUBLIC_APP_URL")
    workers_internal_secret: str = Field(default="", alias="WORKERS_INTERNAL_SECRET")
    cron_secret: str = Field(default="", alias="CRON_SECRET")

    # ----- LiteLLM -----------------------------------------------------------
    litellm_proxy_url: HttpUrl = Field(alias="LITELLM_PROXY_URL")
    litellm_master_key: str = Field(alias="LITELLM_MASTER_KEY")
    litellm_timeout_seconds: float = 60.0

    # ----- Supabase ----------------------------------------------------------
    supabase_url: HttpUrl = Field(alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    # Anon key is acceptable for read-only flows that go through RLS.
    supabase_anon_key: str = Field(alias="NEXT_PUBLIC_SUPABASE_ANON_KEY")

    # ----- Observability -----------------------------------------------------
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")

    # ----- Email (Resend; §3 + §14) ------------------------------------------
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    resend_from_email: str = Field(
        default="Quarrel <noreply@quarrel.ai>", alias="RESEND_FROM_EMAIL"
    )
    support_email: str = Field(default="support@quarrel.ai", alias="SUPPORT_EMAIL")
    # §16 Privacy policy requires a postal address. Dev-default placeholder; set
    # this in production before any non-transactional email goes out.
    legal_address: str = Field(
        default="Quarrel AI, Dhaka, Bangladesh",
        alias="LEGAL_ADDRESS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so repeated imports don't re-parse env on every call."""

    return Settings()
