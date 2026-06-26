"""
独立检测应用配置 —— 只依赖一个 .env，自包含。
换模型只需改 .env 中的 DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY / DEEPSEEK_MODEL。
"""
from functools import lru_cache
from pydantic import field_validator
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

    # 演示「标准样本」：对两个指定演示文件返回已人工核验的检测结果，确保演示稳定。
    # 设 DEMO_GOLDEN=false 可关闭，全部走 LLM 审核。
    demo_golden: bool = True

    # 容错：环境变量值常因复制粘贴带上首尾空白/制表符，统一去掉
    @field_validator("deepseek_base_url", "deepseek_api_key", "deepseek_model", mode="before")
    @classmethod
    def _strip_str(cls, v):
        return v.strip() if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
