"""Logging configuration using loguru with a stdlib fallback."""

import logging as std_logging
import sys
from typing import TYPE_CHECKING, Any

try:
    from loguru import logger as _loguru_logger
except ImportError:  # pragma: no cover
    _loguru_logger = None

if TYPE_CHECKING:
    from tg_agent.config import Settings
else:
    Settings = Any


class _FallbackLogger:
    def __init__(self) -> None:
        self._root = std_logging.getLogger("tg_agent")
        if not self._root.handlers:
            handler = std_logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                std_logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
                )
            )
            self._root.addHandler(handler)
        self._root.setLevel(std_logging.INFO)

    def remove(self) -> None:
        return None

    def add(self, *_args, **kwargs) -> None:
        level = kwargs.get("level")
        if level:
            self._root.setLevel(
                getattr(std_logging, str(level).upper(), std_logging.INFO)
            )

    def bind(self, **kwargs):
        return std_logging.getLogger(kwargs.get("name", "tg_agent"))


logger = _loguru_logger or _FallbackLogger()


def setup_logging(settings: Settings | None = None) -> None:
    """
    Configure loguru logging with console output.

    Args:
        settings: Application settings. If None, loads from environment.
    """
    if settings is None:
        from tg_agent.config import get_settings

        settings = get_settings()

    # Remove default handler
    logger.remove()

    # Add console handler with colored output
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=settings.app_env == "dev",
    )

    # Add file handler for production
    if settings.app_env == "prod":
        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "agent.log",
            format=log_format,
            level=settings.log_level,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            backtrace=False,
            diagnose=False,
        )


def get_logger(name: str = __name__) -> logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name, typically __name__.

    Returns:
        Configured logger instance.
    """
    return logger.bind(name=name)
