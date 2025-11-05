# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "TIARA Engine"
    TIARA_SYNC_KEY_HEX: str  # Wajib ada di .env
    LARAVEL_WEBHOOK_URL: str # URL untuk lapor balik ke Laravel

    @property
    def SYNC_KEY_BYTES(self) -> bytes:
        return bytes.fromhex(self.TIARA_SYNC_KEY_HEX)

    class Config:
        env_file = ".env"

settings = Settings()