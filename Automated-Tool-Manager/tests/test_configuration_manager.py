"""
Unit tests for ConfigurationManager environment, PATH, and executable checks.
"""

import os
from pathlib import Path

import pytest

from modules.configuration_manager import ConfigurationManager
from modules.dependency_checker import ToolAuditResult


def test_detects_missing_and_invalid_env_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    non_existent = str(tmp_path / "missing_esim_dir")
    monkeypatch.setenv("ESIM_HOME", non_existent)

    specs = [
        {"name": "ESIM_HOME", "required": True},
        {"name": "UNSET_CUSTOM_VAR", "required": False},
    ]
    cm = ConfigurationManager(env_specs=specs)
    checked, issues = cm.check_environment_variables()

    assert checked["ESIM_HOME"] == non_existent
    assert checked["UNSET_CUSTOM_VAR"] is None
    assert len(issues) == 2
    assert any(i.target == "ESIM_HOME" and i.severity == "ERROR" for i in issues)
    assert any(i.target == "UNSET_CUSTOM_VAR" and i.severity == "WARNING" for i in issues)


def test_detects_stale_and_duplicate_path_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    valid_dir = tmp_path / "bin"
    valid_dir.mkdir()
    stale_dir = tmp_path / "ghost_bin"

    fake_path = os.pathsep.join([str(valid_dir), str(valid_dir), str(stale_dir)])
    monkeypatch.setenv("PATH", fake_path)

    cm = ConfigurationManager()
    issues = cm.check_system_path()

    assert any("duplicate" in i.message.lower() for i in issues)
    assert any("do not exist" in i.message.lower() for i in issues)


def test_verifies_executable_permissions_and_missing_binaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_bin = tmp_path / "ngspice"
    fake_bin.write_text("#!/bin/sh\necho ngspice", encoding="utf-8")

    # Force os.access to return False to simulate non-executable file cross-platform
    monkeypatch.setattr("os.access", lambda path, mode: False)

    audit = [
        ToolAuditResult(
            id="ngspice",
            name="Ngspice",
            required=True,
            installed=True,
            executable_used="ngspice",
            executable_path=str(fake_bin),
        )
    ]
    cm = ConfigurationManager()
    issues = cm.verify_tool_executables(audit)

    assert len(issues) == 1
    assert issues[0].category == "EXECUTABLE_PERM"
    assert "lacks execute permission" in issues[0].message