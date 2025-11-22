# core/config.py
import base64
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "TIARA Engine"
    TIARA_SYNC_KEY: str
    TIARA_WEBHOOK_URL: str
    LOG_LEVEL: str = "INFO"

    @property
    def SYNC_KEY_BYTES(self) -> bytes:
        # Fungsi ini sekarang bisa membaca format APP_KEY Laravel
        if self.TIARA_SYNC_KEY.startswith('base64:'):
            key_base64 = self.TIARA_SYNC_KEY[7:]
            return base64.b64decode(key_base64)
        else:
            # Jika tidak ada prefix, anggap itu raw string (meski tidak disarankan)
            return self.TIARA_SYNC_KEY.encode('utf-8')

    class Config:
        env_file = ".env"

settings = Settings()