"""
Second Brain Backend Configuration
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # AI Provider
    ai_provider: str = os.getenv("AI_PROVIDER", "gemini")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # Paths
    vault_path: str = os.getenv("VAULT_PATH", "./vault")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")

    # Limits
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    @property
    def vault_abs_path(self) -> Path:
        return Path(self.vault_path).resolve()

    @property
    def upload_abs_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
