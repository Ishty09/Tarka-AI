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

    # ----- Push (Web Push + Expo; §3 + §13) ---------------------------------
    # VAPID keys for Web Push (RFC 8292). Both must be set for real delivery
    # to browsers; until then `_DryRunWebPushSender` no-ops with a log line.
    vapid_public_key: str = Field(default="", alias="VAPID_PUBLIC_KEY")
    vapid_private_key: str = Field(default="", alias="VAPID_PRIVATE_KEY")
    vapid_subject: str = Field(default="mailto:noreply@quarrel.ai", alias="VAPID_SUBJECT")
    # Optional Expo access token — raises the per-hour rate limit.
    expo_access_token: str = Field(default="", alias="EXPO_ACCESS_TOKEN")

    # ----- Polar (web subscriptions; §3 + §8) -------------------------------
    polar_webhook_secret: str = Field(default="", alias="POLAR_WEBHOOK_SECRET")
    polar_product_id_pro_monthly: str = Field(default="", alias="POLAR_PRODUCT_ID_PRO_MONTHLY")
    polar_product_id_pro_annual: str = Field(default="", alias="POLAR_PRODUCT_ID_PRO_ANNUAL")
    polar_product_id_max_monthly: str = Field(default="", alias="POLAR_PRODUCT_ID_MAX_MONTHLY")
    polar_product_id_max_annual: str = Field(default="", alias="POLAR_PRODUCT_ID_MAX_ANNUAL")

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
