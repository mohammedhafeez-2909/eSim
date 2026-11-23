"""
Unit tests for the ActivityLogger module and config/tools.json manifest.
"""

import json
import logging
from pathlib import Path

from modules.logger import ActivityLogger


def test_tools_config_is_valid_json() -> None:
    """Verify config/tools.json loads cleanly and contains expected schema keys."""
    config_path = Path("config/tools.json")
    assert config_path.exists(), "config/tools.json must exist"

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert "tools" in data
    assert "environment_variables" in data
    assert len(data["tools"]) >= 5

    required_keys = {
        "id",
        "name",
        "executable",
        "version_flag",
        "version_regex",
        "min_version",
        "recommended_version",
        "required",
        "packages",
    }
    for tool in data["tools"]:
        assert required_keys.issubset(tool.keys()), f"Missing keys in {tool.get('id')}"


def test_activity_logger_creates_log_file_and_records_messages(tmp_path: Path) -> None:
    """Verify ActivityLogger writes formatted entries and reads recent logs."""
    activity_logger = ActivityLogger(
        name="TestLoggerInstance",
        log_dir=str(tmp_path),
        log_filename="test_audit.log",
        console_level=logging.ERROR,
        file_level=logging.DEBUG,
    )
    logger = activity_logger.get_logger()
    logger.info("Dependency scan started")
    logger.warning("Ngspice binary not found in PATH")

    assert activity_logger.log_file.exists()

    recent = activity_logger.read_recent_logs(lines=5)
    assert len(recent) == 2
    assert "INFO" in recent[0]
    assert "Dependency scan started" in recent[0]
    assert "WARNING" in recent[1]
    assert "Ngspice binary not found in PATH" in recent[1]


def test_read_recent_logs_when_file_missing(tmp_path: Path) -> None:
    """Verify read_recent_logs returns an empty list if log file was deleted."""
    activity_logger = ActivityLogger(
        name="MissingFileLogger",
        log_dir=str(tmp_path),
        log_filename="temp.log",
    )
    activity_logger.close()
    activity_logger.log_file.unlink(missing_ok=True)
    assert activity_logger.read_recent_logs() == []