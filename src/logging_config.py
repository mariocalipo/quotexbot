import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_dir = Path(os.getenv("LOG_DIR", Path(__file__).parent.parent / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_dir / "quotexbot.log",
        maxBytes=int(os.getenv("LOG_MAX_BYTES", "10485760")),  # 10 MB
        backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5"))
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
