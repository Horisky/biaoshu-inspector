"""
独立检测应用配置 —— 只依赖一个 .env，自包含。
换模型只需改 .env 中的 DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY / DEEPSEEK_MODEL。
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 服务
    host: str = "0.0.0.0"
    port: int = 8100

    # LLM（OpenAI 兼容接口，默认 DeepSeek，可指向中转站）
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # 上传限制
    max_upload_mb: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
