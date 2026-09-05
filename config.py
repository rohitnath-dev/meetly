from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Project
    PROJECT_NAME: str = "Meetly"
    VERSION: str = "1.0.0"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4-turbo"
    OPENROUTER_TIMEOUT: float = 60.0
    OPENROUTER_TEMPERATURE: float = 0.2
    OPENROUTER_MAX_TOKENS: int = 2000

    # Google Meet
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""

    # App Metadata
    APP_TITLE: str = "Meetly"
    HTTP_REFERER: str = "https://meetly.ai"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def has_google_credentials(self) -> bool:
        """Check if Google credentials are configured."""
        return bool(
            self.GOOGLE_CLIENT_ID
            and self.GOOGLE_CLIENT_SECRET
            and self.GOOGLE_REFRESH_TOKEN
        )

    def has_openrouter_credentials(self) -> bool:
        """Check if OpenRouter credentials are configured."""
        return bool(self.OPENROUTER_API_KEY)


settings = Settings()
