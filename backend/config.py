from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
	# Database configuration (loaded from .env)
	DB_HOST: str
	DB_PORT: int
	DB_USER: str
	DB_PASSWORD: str
	DB_NAME: str
	google_cloud_api_key: str | None = None
	MEDIA_ROOT: str = str((Path(__file__).resolve().parent.parent / "ingest" / "media").resolve())
	MEDIA_URL_BASE: str = "/media"

	ENVIRONMENT: str = "development"

	@property
	def DATABASE_URL(self) -> str:
		return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

	class Config:
		env_file = ".env"
		env_file_encoding = 'utf-8'


@lru_cache()
def get_settings() -> Settings:
	return Settings()
