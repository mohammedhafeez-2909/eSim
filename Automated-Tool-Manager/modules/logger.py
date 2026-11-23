"""
Activity Logger Module for eSim Automated Tool Manager.

Provides centralized, structured logging across all application modules using
Python's built-in `logging` framework with rotating file handlers and clean
console output separation.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ActivityLogger:
    """
    Configures and manages application-wide activity logging.

    Attributes:
        log_dir (Path): Directory where log files are stored.
        log_file (Path): Full path to the active log file.
        logger (logging.Logger): Configured Python logger instance.
    """

    def __init__(
        self,
        name: str = "eSimToolManager",
        log_dir: str = "logs",
        log_filename: str = "tool_manager.log",
        console_level: int = logging.WARNING,
        file_level: int = logging.DEBUG,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / log_filename

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers if ActivityLogger is instantiated multiple times
        if not self.logger.handlers:
            self._setup_handlers(console_level, file_level)

    def _setup_handlers(self, console_level: int, file_level: int) -> None:
        """Attach rotating file handler and console stream handler."""
        detailed_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_formatter = logging.Formatter(
            fmt="[%(levelname)s] %(message)s"
        )

        # Rotating file handler: max 2 MB per file, keeps 3 backups
        file_handler = RotatingFileHandler(
            self.log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(detailed_formatter)

        # Console handler: only prints WARNING/ERROR so CLI menus stay uncluttered
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(console_formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_logger(self) -> logging.Logger:
        """Return the underlying configured Logger instance."""
        return self.logger

    def read_recent_logs(self, lines: int = 20) -> list[str]:
        """
        Retrieve the last `lines` entries from the active log file.

        Args:
            lines: Number of trailing log lines to return.

        Returns:
            List of log strings (empty list if file does not exist).
        """
        if not self.log_file.exists():
            return []
        with self.log_file.open("r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return [line.rstrip("\n") for line in all_lines[-lines:]]
    def close(self) -> None:
        """Close and detach all logging handlers to release open file locks."""
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)


def get_app_logger(
    log_dir: str = "logs", log_filename: str = "tool_manager.log"
) -> logging.Logger:
    """Convenience factory returning the singleton application logger."""
    return ActivityLogger(log_dir=log_dir, log_filename=log_filename).get_logger()