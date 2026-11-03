"""Application request logging with rotating local log files.

Never log request bodies, authorization headers, cookies, or payment payloads.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    if any(getattr(handler, "_myfarmgrows_handler", False) for handler in root_logger.handlers):
        return

    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler._myfarmgrows_handler = True
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    root_logger.addHandler(logging.StreamHandler())
