"""
Centralized logging so every error is captured with context, both to
console (for platform logs like Render/Railway) and to a rotating file.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from app.config import settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(settings.LOG_LEVEL)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        log_path = os.path.join(settings.LOG_DIR, "app.log")
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # If the filesystem is read-only (some serverless hosts), just skip file logging.
        logger.warning("File logging disabled (read-only filesystem or permission error).")

    logger.propagate = False
    return logger
