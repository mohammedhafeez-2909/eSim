"""
Unit tests for DependencyChecker using pytest monkeypatch/mocks.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from modules.dependency_checker import DependencyChecker


@pytest.fixture
def sample_config(tmp_path: Path) -> Path:
    """Create a temporary tools.json configuration for isolated testing."""
    cfg = {
        "tools": [
            {
                "id": "ngspice",
                "name": "Ngspice Circuit Simulator",
                "executable": "ngspice",
                "alt_executables": ["ngspice_con"],
                "version_flag": "--version",
                "version_regex": r"ngspice[-\s]+(\d+(?:\.\d+)*)",
                "min_version": "34.0",
                "recommended_version": "42.0",
                "required": True,
                "packages": {"linux_apt": "ngspice"},
            },
            {
                "id": "kicad",
                "name": "KiCad EDA",
                "executable": "kicad-cli",
                "alt_executables": ["kicad"],
                "version_flag": "--version",
                "version_regex": r"(\d+\.\d+\.\d+)",
                "min_version": "6.0.0",
                "recommended_version": "8.0.0",
                "required": True,
                "packages": {"linux_apt": "kicad"},
            },
        ]
    }
    config_file = tmp_path / "tools.json"
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    return config_file


def test_detects_installed_and_missing_tools(
    sample_config: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify installed tools resolve version while missing tools report installed=False."""

    def fake_which(binary: str) -> Optional[str]:
        if binary == "ngspice":
            return "/usr/bin/ngspice"
        return None

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="ngspice-42 : Circuit level simulation program\n",
            stderr="",
        )

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)

    checker = DependencyChecker(config_path=str(sample_config))
    results = checker.check_all_dependencies()

    assert len(results) == 2

    ngspice_res = results[0]
    assert ngspice_res.installed is True
    assert ngspice_res.executable_used == "ngspice"
    assert ngspice_res.installed_version == "42"

    kicad_res = results[1]
    assert kicad_res.installed is False
    assert kicad_res.executable_path is None

    report_path = tmp_path / "report.json"
    report = checker.generate_report(results, export_path=str(report_path))
    assert report_path.exists()
    assert report["summary"]["installed_count"] == 1
    assert report["summary"]["missing_required"] == ["KiCad EDA"]
    assert report["summary"]["ready_for_esim"] is False


def test_handles_subprocess_timeout_gracefully(
    sample_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a hanging tool version command does not crash the scanner."""
    monkeypatch.setattr("shutil.which", lambda binary: "/usr/bin/ngspice" if binary == "ngspice" else None)

    def raise_timeout(cmd: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    monkeypatch.setattr("subprocess.run", raise_timeout)

    checker = DependencyChecker(config_path=str(sample_config))
    res = checker.check_single_tool(checker.config_data["tools"][0])

    assert res.installed is True
    assert res.installed_version is None
    assert res.error is not None and "Timed out" in res.error


def test_missing_config_raises_file_not_found() -> None:
    """Verify missing configuration path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        DependencyChecker(config_path="config/non_existent_tools.json")