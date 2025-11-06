# core/config.py
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "TIARA Engine"
    TIARA_SYNC_KEY_HEX: str             
    LARAVEL_WEBHOOK_URL: str            
    LOG_LEVEL: str = "INFO"             

    @property
    def SYNC_KEY_BYTES(self) -> bytes:
        return bytes.fromhex(self.TIARA_SYNC_KEY_HEX)

    class Config:
        env_file = ".env"


settings = Settings()
