from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Vela 出海法务平台"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    database_url: str = "sqlite:///./data/vela.db"
    chroma_persist_dir: str = "./data/chroma"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://127.0.0.1:8000"

    allow_open_registration: bool = True
    allow_password_login: bool = True

    # SSO (OpenID Connect)
    sso_enabled: bool = False
    sso_provider_name: str = "企业 SSO"
    sso_issuer_url: str = ""
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_redirect_uri: str = ""
    sso_scopes: str = "openid profile email"
    sso_default_role: str = "legal"
    sso_jit_provision: bool = True

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
    llm_polish_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
