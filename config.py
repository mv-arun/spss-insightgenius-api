"""Application configuration via environment variables."""

import json
import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # App
    app_name: str = "Indico Crosstab API"
    app_env: str = "development"
    app_version: str = "1.0.0"
    port: int = 8000

    # Auth — JSON array of key configs
    # Format: [{"key_hash":"sha256hex","name":"Acme","plan":"pro","scopes":["process","metadata",...]}]
    api_keys_json: str = "[]"

    # TESTING ONLY — when true, requests without an Authorization header are
    # treated as an anonymous user with all scopes. Requests that DO send a key
    # are still validated normally. /v1/keys always requires a real key.
    auth_disabled: bool = False

    # Claude AI (Haiku for ticket parsing + smart labeling)
    anthropic_api_key: str = ""

    # Rate limits per plan (requests/minute)
    rate_limit_free: int = 10
    rate_limit_pro: int = 60
    rate_limit_business: int = 200

    # File limits
    max_file_size_mb: int = 100

    # Processing
    processing_timeout_seconds: int = 120
    max_concurrent_processing: int = 3  # max SPSS files processing per worker

    # Redis (for distributed rate limiting + MCP file sessions — optional)
    redis_url: str = ""

    # Demo API key for embedded frontend (not in repo — set in Railway env vars)
    demo_api_key: str = ""

    # Web UI sign-in — one shared account until real user accounts exist.
    # Sign-in is refused while email or password is unset.
    ui_login_email: str = ""
    ui_login_password: str = ""
    ui_login_name: str = ""  # shown in the top bar; falls back to the email
    ui_session_secret: str = ""  # signs the session cookie; derived from the credentials if unset
    ui_session_hours: int = 12

    # MCP file sessions
    spss_session_ttl_seconds: int = 1800  # 30 minutes sliding window
    redis_max_file_size_mb: int = 100
    # Parsed files kept in each worker's memory (services/data_cache.py); 0 turns the cache off
    parsed_cache_mb: int = 512

    # Clerk (OAuth 2.0 auth provider)
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    clerk_jwt_issuer: str = ""  # Auto-detected from publishable key if empty
    clerk_domain: str = ""  # e.g., "beloved-redbird-68.clerk.accounts.dev" or "clerk.indicolabs.io"

    # Optional features, off for the MVP. Datasets (the saved-file library) needs Supabase;
    # AI chat needs ANTHROPIC_API_KEY. Off: their API routes and pages aren't served.
    enable_datasets: bool = False
    enable_ai_chat: bool = False

    # Supabase (user data, API keys, usage tracking)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Base URL for download links
    base_url: str = "https://crosstab.indicolabs.io"

    # CORS — production origins only; override with CORS_ORIGINS env var
    cors_origins: str = '["https://crosstab.indicolabs.io", "https://talk2data.indicolabs.io", "https://claude.ai"]'

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def parsed_api_keys(self) -> list[dict]:
        try:
            return json.loads(self.api_keys_json)
        except json.JSONDecodeError:
            logger.error("Failed to parse API_KEYS_JSON")
            return []

    @property
    def parsed_cors_origins(self) -> list[str]:
        try:
            origins = json.loads(self.cors_origins)
            return origins if isinstance(origins, list) else ["https://crosstab.indicolabs.io"]
        except json.JSONDecodeError:
            return ["https://crosstab.indicolabs.io"]

    @property
    def clerk_frontend_api(self) -> str:
        """Derive Clerk Frontend API URL from publishable key or explicit domain."""
        if self.clerk_domain:
            return f"https://{self.clerk_domain}"
        if self.clerk_publishable_key:
            # pk_test_<base64_domain>$ → decode to get domain
            import base64
            try:
                encoded = self.clerk_publishable_key.split("_", 2)[-1].rstrip("$")
                # Add padding
                padding = 4 - len(encoded) % 4
                if padding != 4:
                    encoded += "=" * padding
                domain = base64.b64decode(encoded).decode("utf-8").rstrip("$").strip()
                return f"https://{domain}"
            except Exception:
                pass
        return ""

    @property
    def clerk_jwks_url(self) -> str:
        """JWKS URL for validating Clerk JWTs."""
        frontend = self.clerk_frontend_api
        return f"{frontend}/.well-known/jwks.json" if frontend else ""

    def rate_limit_for_plan(self, plan: str) -> int:
        limits = {
            "free": self.rate_limit_free,
            "pro": self.rate_limit_pro,
            "business": self.rate_limit_business,
        }
        return limits.get(plan, self.rate_limit_free)


@lru_cache
def get_settings() -> Settings:
    return Settings()
