from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    database_url: str
    order_database_url: str

    secret_key: SecretStr
    algorithm: str
    jwt_expire_minutes: int = Field(gt=0)

    gateway_secret: SecretStr
    user_service_url: str
    order_service_url: str
    upstream_timeout_seconds: float = Field(gt=0)

    minio_endpoint: str
    minio_public_endpoint: str
    minio_access_key: str
    minio_secret_key: SecretStr
    minio_secure: bool
    minio_bucket: str
    minio_region: str


settings = Settings()
