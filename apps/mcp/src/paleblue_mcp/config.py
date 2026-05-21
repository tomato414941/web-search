import os


class Settings:
    """MCP server configuration from environment variables."""

    def __init__(self):
        self.base_url = os.getenv(
            "PALEBLUE_BASE_URL", "https://palebluesearch.com"
        ).rstrip("/")
        self.api_key = os.getenv("PALEBLUE_API_KEY", "")
        self.timeout = float(os.getenv("PALEBLUE_TIMEOUT", "30"))


settings = Settings()
