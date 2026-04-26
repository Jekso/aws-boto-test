"""Application entry point."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from street_incidents.config import ConfigLoader
from street_incidents.logging_config import configure_logging
from street_incidents.services.runner import ApplicationRunner


def main() -> None:
    """Run the application."""
    config = ConfigLoader().load()
    configure_logging(Path(config.log_dir))
    logger.info("Loaded configuration for {} cameras.", len(config.cameras))
    runner = ApplicationRunner(config)
    runner.run()


if __name__ == "__main__":
    main()
