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

    # LLM polish (DeepSeek preferred; Qwen/DashScope as fallback)
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
    def data_dir(self) -> Path:
        path = Path("./data")
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
