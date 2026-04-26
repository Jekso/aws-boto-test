"""Project logging configuration."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(log_dir: Path) -> None:
    """Configure Loguru sinks.

    Args:
        log_dir: Directory where rotating log files are stored.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
    )
    logger.add(
        log_dir / "street_incidents.log",
        level="DEBUG",
        rotation="20 MB",
        retention=10,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    )
