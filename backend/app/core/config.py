from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secret_policy import is_placeholder_value, is_weak_secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Vela 出海法务平台"
    app_env: str = "development"
    vela_app_mode: str = "development"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    database_url: str = "sqlite:///./data/vela.db"
    chroma_persist_dir: str = "./data/chroma"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://127.0.0.1:8000"

    # The current release is intentionally scoped to one customer/organisation
    # per deployment.  A multi-tenant mode must not be enabled until tenant ids
    # and row-level authorisation exist across every persisted resource.
    deployment_mode: str = "single_tenant"
    instance_organization: str = ""

    allow_open_registration: bool = True
    allow_password_login: bool = True
    rate_limit_enabled: bool = False

    # SSO (OpenID Connect)
    sso_enabled: bool = False
    sso_provider_name: str = "企业 SSO"
    sso_issuer_url: str = ""
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_redirect_uri: str = ""
    sso_scopes: str = "openid profile email"
    sso_default_role: str = "business"
    sso_jit_provision: bool = True
    sso_groups_claim: str = "groups"
    sso_admin_groups: str = ""
    sso_legal_groups: str = ""
    sso_business_groups: str = ""
    sso_require_verified_email: bool = True

    # Word export template: legacy | law_school
    export_template: str = "law_school"
    export_org_name: str = "Vela 出海法务台 · 法学院合规研究格式"
    export_org_department: str = "企业法务部 / 合规研究中心"
    export_recipient_label: str = "企业管理层 / 投资委员会"

    # LLM polish
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    llm_polish_enabled: bool = False

    # Agent / tier gate (Legal-Skills-inspired)
    match_threshold_default: int = 70
    retrieval_top_k_default: int = 3
    corpus_agent_interval_hours: int = 6
    corpus_agent_enabled: bool = False
    tier_s3_hard_block: bool = True
    agent_polish_default: bool = False

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return normalized

    @field_validator("vela_app_mode", mode="before")
    @classmethod
    def normalize_vela_app_mode(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"development", "competition"}:
            raise ValueError("VELA_APP_MODE must be development or competition")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_competition(self) -> bool:
        return self.vela_app_mode == "competition"

    @property
    def sso_configured(self) -> bool:
        return bool(
            self.sso_enabled
            and self.sso_issuer_url
            and self.sso_client_id
            and self.sso_client_secret
            and self.sso_redirect_uri
        )

    @property
    def data_dir(self) -> Path:
        path = Path("./data")
        path.mkdir(parents=True, exist_ok=True)
        return path


def validate_runtime_configuration(settings: Settings | None = None) -> None:
    """Fail closed when a production deployment exceeds the audited boundary.

    The application currently supports an isolated, single-tenant pilot.  SSO,
    background corpus mutation and automatic third-party LLM egress remain
    available only for development until their dedicated security controls are
    implemented and independently verified.
    """

    settings = settings or get_settings()
    if settings.is_competition:
        parsed_database = urlsplit(settings.database_url)
        if parsed_database.scheme.lower() != "sqlite" or Path(parsed_database.path).name != "vela_competition.db":
            raise RuntimeError(
                "competition mode requires the isolated vela_competition.db SQLite database"
            )
    if not settings.is_production:
        return

    errors: list[str] = []
    if settings.debug:
        errors.append("DEBUG must be false")
    if settings.algorithm != "HS256":
        errors.append("ALGORITHM must be HS256")
    if not 5 <= settings.access_token_expire_minutes <= 60:
        errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 60")
    if settings.deployment_mode != "single_tenant":
        errors.append("DEPLOYMENT_MODE must be single_tenant for this release")
    if not settings.instance_organization.strip():
        errors.append("INSTANCE_ORGANIZATION must identify the only organisation in this instance")
    elif is_placeholder_value(settings.instance_organization):
        errors.append("INSTANCE_ORGANIZATION must not be a copied example or placeholder")
    elif len(settings.instance_organization.strip()) > 255:
        errors.append("INSTANCE_ORGANIZATION must be at most 255 characters")
    if settings.allow_open_registration:
        errors.append("ALLOW_OPEN_REGISTRATION must be false")
    if not settings.rate_limit_enabled:
        errors.append("RATE_LIMIT_ENABLED must be true")
    if settings.sso_enabled:
        errors.append("SSO_ENABLED must remain false until the hardened OIDC flow ships")
    if settings.corpus_agent_enabled:
        errors.append("CORPUS_AGENT_ENABLED must be false in web processes")
    if settings.llm_polish_enabled:
        errors.append("LLM_POLISH_ENABLED must be false for the controlled pilot")
    if not settings.allow_password_login:
        errors.append("ALLOW_PASSWORD_LOGIN must be true while production SSO is disabled")
    if is_weak_secret(settings.secret_key, min_length=32, min_unique=8):
        errors.append(
            "SECRET_KEY must be a non-default value of at least 32 characters with adequate diversity"
        )
    if "*" in settings.cors_origin_list:
        errors.append("CORS_ORIGINS must not contain a wildcard")
    for label, url in (
        ("FRONTEND_URL", settings.frontend_url),
        ("PUBLIC_API_URL", settings.public_api_url),
        *(("CORS_ORIGINS", origin) for origin in settings.cors_origin_list),
    ):
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        loopback = host in {"localhost", "127.0.0.1", "::1"}
        if not loopback and parsed.scheme.lower() != "https":
            errors.append(f"{label} must use HTTPS unless it is loopback-only")

    if errors:
        raise RuntimeError("unsafe production configuration: " + "; ".join(errors))


def is_instance_organization_member(
    organization: str | None,
    settings: Settings | None = None,
) -> bool:
    """Reject legacy or imported cross-organisation accounts in production."""

    settings = settings or get_settings()
    if not settings.is_production:
        return True
    return bool(
        settings.instance_organization.strip()
        and (organization or "").strip() == settings.instance_organization.strip()
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
