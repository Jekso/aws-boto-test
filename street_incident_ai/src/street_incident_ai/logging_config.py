from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: str | Path = "logs", level: str = "INFO") -> None:
    """Configure loguru console and rotating file logs.

    Args:
        log_dir: Directory where log files will be written.
        level: Minimum log level, for example DEBUG or INFO.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        Path(log_dir) / "app.log",
        level=level,
        rotation="20 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    )
