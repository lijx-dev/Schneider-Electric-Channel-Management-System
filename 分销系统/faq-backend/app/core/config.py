"""Application settings."""
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "分销商FAQ系统"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    DB_TYPE: str = "memory"
    DATABASE_URL: Optional[str] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    ENABLE_MONTHLY_REWARD_SCHEDULER: bool = False
    MONTHLY_REWARD_CHECK_INTERVAL_SECONDS: int = 21600

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_SECRET_KEY: Optional[str] = None

    WECHAT_APPID: Optional[str] = None
    WECHAT_SECRET: Optional[str] = None
    WECHAT_SSL_VERIFY: bool = True
    WECHAT_CA_BUNDLE: Optional[str] = None
    WECHAT_HTTP_TRUST_ENV: bool = False

    HIAGENT_API_BASE: str = "https://hiagent-stg.schneider-electric.cn/api/proxy/api/v1"
    HIAGENT_API_KEY: Optional[str] = None
    HIAGENT_FEEDBACK_PATH: str = "/feedback"
    HIAGENT_LIKE_TYPE: int = 1
    HIAGENT_DISLIKE_TYPE: int = -1

    # RAGFlow 文档检索引擎配置
    RAGFLOW_API_BASE: str = "http://localhost:9380/api/v1"
    RAGFLOW_API_KEY: Optional[str] = None
    # 知识库 ID：事实层（PDF 电气参数）、话术层、友商层、通用知识层
    RAGFLOW_KNOWLEDGE_BASE_ID: Optional[str] = None           # 事实层（默认）
    RAGFLOW_TALK_KB_ID: Optional[str] = None                  # 话术层
    RAGFLOW_COMPETITOR_KB_ID: Optional[str] = None            # 友商层
    RAGFLOW_GENERAL_KB_ID: Optional[str] = None               # 通用知识层
    RAGFLOW_ENABLED: bool = True
    RAGFLOW_RETRIEVAL_TOP_K: int = 5
    RAGFLOW_SIMILARITY_THRESHOLD: float = 0.2

    STORAGE_BACKEND: str = "local"
    COS_SECRET_ID: Optional[str] = None
    COS_SECRET_KEY: Optional[str] = None
    COS_SESSION_TOKEN: Optional[str] = None
    COS_REGION: Optional[str] = "ap-shanghai"
    COS_BUCKET: Optional[str] = "7465-test-8gwkg5zb84a8b224-1407839340"
    COS_BASE_URL: Optional[str] = None
    COS_SIGN_EXPIRE_SECONDS: int = 3600

    CORS_ORIGINS: str = "https://servicewechat.com"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def storage_backend(self) -> str:
        backend = (self.STORAGE_BACKEND or "local").lower()
        if (
            backend == "local"
            and self.COS_SECRET_ID
            and self.COS_SECRET_KEY
            and self.COS_REGION
            and self.COS_BUCKET
        ):
            return "cos"
        return backend

    @property
    def storage_public_base_url(self) -> str:
        if self.COS_BASE_URL:
            return self.COS_BASE_URL.rstrip("/")
        if self.COS_BUCKET and self.COS_REGION:
            return f"https://{self.COS_BUCKET}.cos.{self.COS_REGION}.myqcloud.com"
        return ""

    @property
    def admin_secret_key(self) -> str:
        return self.ADMIN_SECRET_KEY or self.SECRET_KEY

    def validate_runtime_requirements(self) -> None:
        if not self.is_production:
            return

        if not self.SECRET_KEY or self.SECRET_KEY == "change-me-in-production":
            raise RuntimeError("生产环境必须配置安全的 SECRET_KEY")

        if self.DB_TYPE != "mysql" or not self.DATABASE_URL:
            raise RuntimeError("生产环境必须使用 MySQL，并配置 DATABASE_URL")

        if self.storage_backend != "cos":
            raise RuntimeError("生产环境头像存储必须使用对象存储（STORAGE_BACKEND=cos）")

        required_cos = {
            "COS_SECRET_ID": self.COS_SECRET_ID,
            "COS_SECRET_KEY": self.COS_SECRET_KEY,
            "COS_REGION": self.COS_REGION,
            "COS_BUCKET": self.COS_BUCKET,
        }
        missing = [name for name, value in required_cos.items() if not value]
        if missing:
            raise RuntimeError(f"生产环境对象存储配置缺失: {', '.join(missing)}")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
