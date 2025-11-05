import logging
import logging.config
import os
from core.config import settings

# --- Filter Kustom ---
class LevelFilter(logging.Filter):
    """Filter ini HANYA mengizinkan record log dengan level yang SAMA PERSIS."""
    def __init__(self, level):
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno == self.level

# --- Formatter Kustom ---
class CustomFormatter(logging.Formatter):
    """Formatter kustom untuk meratakan kolom nama logger secara dinamis."""
    LEVEL_WIDTH = 8  # Sedikit diperlebar untuk CRITICAL
    NAME_WIDTH = 25  # Disesuaikan agar tidak terlalu lebar

    def format(self, record):
        # Persingkat nama logger agar rapi (misal: tiara_engine.modules.ssl -> modules.ssl)
        logger_name = record.name.replace("tiara_engine.", "")
        if len(logger_name) > self.NAME_WIDTH:
             logger_name = "..." + logger_name[-(self.NAME_WIDTH - 3):]

        log_entry = (
            f"{self.formatTime(record, self.datefmt)} | "
            f"{record.levelname:<{self.LEVEL_WIDTH}} | "
            f"{logger_name:<{self.NAME_WIDTH}} | "
            f"{record.getMessage()}"
        )
        return log_entry

# --- Fungsi Setup Utama ---
def setup_logging():
    """Mengkonfigurasi logging aplikasi berdasarkan settings."""
    
    # Pastikan folder logs ada
    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)

    # Tentukan level log root dari settings (default INFO jika tidak diset)
    ROOT_LEVEL = getattr(settings, "LOG_LEVEL", "INFO").upper()

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "custom": {
                "()": CustomFormatter,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "standard": { # Formatter cadangan yang lebih simpel
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            "info_only": {"()": LevelFilter, "level": logging.INFO},
            "debug_only": {"()": LevelFilter, "level": logging.DEBUG}, # Tambahan jika butuh file khusus debug saja
        },
        "handlers": {
            # 1. Console Handler: Tampilkan INFO ke atas di layar
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "custom",
                "level": "INFO", 
                "stream": "ext://sys.stdout", # Pastikan output ke stdout
            },
            # 2. Info File Handler: HANYA mencatat level INFO (bersih dari error/debug)
            "info_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "custom",
                "filename": os.path.join(LOG_DIR, "info.log"),
                "maxBytes": 10_485_760, # 10MB
                "backupCount": 5,
                "encoding": "utf8",
                "level": "INFO",
                "filters": ["info_only"], # KUNCI: Pakai filter info_only
            },
            # 3. Error File Handler: Mencatat WARNING, ERROR, CRITICAL
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "custom",
                "filename": os.path.join(LOG_DIR, "error.log"),
                "maxBytes": 10_485_760,
                "backupCount": 5,
                "encoding": "utf8",
                "level": "WARNING", 
            },
            # 4. Debug File Handler: Mencatat SEMUA detail (jika ROOT_LEVEL=DEBUG)
            "debug_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard", # Gunakan standard agar lebih detail untuk debug
                "filename": os.path.join(LOG_DIR, "debug.log"),
                "maxBytes": 10_485_760,
                "backupCount": 3,
                "encoding": "utf8",
                "level": "DEBUG",
            },
        },
        # Konfigurasi logger pihak ketiga agar tidak terlalu berisik
        "loggers": {
            "uvicorn.access": {"level": "INFO", "propagate": False, "handlers": ["console"]},
            "uvicorn.error": {"level": "INFO", "propagate": False, "handlers": ["console"]},
            "paramiko": {"level": "WARNING"}, # Paramiko bisa sangat berisik di level DEBUG
        },
        # Root Logger: Muara dari semua log
        "root": {
            "level": ROOT_LEVEL, 
            "handlers": ["console", "info_file", "error_file", "debug_file"],
        },
    }

    # Terapkan konfigurasi
    logging.config.dictConfig(LOGGING_CONFIG)
    
    # Log pesan pertama untuk memastikan semua berjalan
    logging.getLogger("tiara_engine.core.logging").info("Sistem logging berhasil diinisialisasi.")