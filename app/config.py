from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    ENV: str = "local"
    API_PREFIX: str = "/api"

    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    JWT_SECRET: str = "CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24


settings = Settings()
