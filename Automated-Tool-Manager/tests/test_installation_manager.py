"""
Unit tests for InstallationManager using mocks so no real software is installed.
"""

import subprocess
from typing import Optional

import pytest

from modules.dependency_checker import ToolAuditResult
from modules.installation_manager import InstallationManager


def _missing_ngspice(pkg_map: Optional[dict[str, str]] = None) -> ToolAuditResult:
    return ToolAuditResult(
        id="ngspice",
        name="Ngspice Circuit Simulator",
        required=True,
        installed=False,
        packages=pkg_map
        if pkg_map is not None
        else {"linux_apt": "ngspice", "windows_winget": "ngspice.ngspice"},
    )


def test_dry_run_mode_does_not_execute_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/apt-get" if b == "apt-get" else None)

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess.run must never execute in dry-run mode!")

    monkeypatch.setattr("subprocess.run", fail_if_called)

    installer = InstallationManager(dry_run=True)
    result = installer.install_tool(_missing_ngspice())

    assert result.status == "DRY_RUN"
    assert result.command == ["sudo", "apt-get", "install", "-y", "ngspice"]


def test_user_cancellation_blocks_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/apt-get" if b == "apt-get" else None)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Should not run when declined")),
    )

    installer = InstallationManager(dry_run=False, confirm_callback=lambda prompt: False)
    result = installer.install_tool(_missing_ngspice())

    assert result.status == "CANCELLED"


def test_confirmed_installation_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/apt-get" if b == "apt-get" else None)

    # 1. Simulate successful install
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="Done", stderr=""),
    )
    installer = InstallationManager(dry_run=False, confirm_callback=lambda prompt: True)
    ok_res = installer.install_tool(_missing_ngspice())
    assert ok_res.status == "INSTALLED"
    assert ok_res.return_code == 0

    # 2. Simulate failed install (non-zero exit code)
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kw: subprocess.CompletedProcess(
            cmd, 100, stdout="", stderr="E: Unable to locate package ngspice"
        ),
    )
    fail_res = installer.install_tool(_missing_ngspice())
    assert fail_res.status == "FAILED"
    assert fail_res.return_code == 100
    assert "Unable to locate package" in fail_res.message


def test_blocks_malicious_package_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/apt-get" if b == "apt-get" else None)

    installer = InstallationManager(dry_run=False, confirm_callback=lambda prompt: True)
    malicious_tool = _missing_ngspice(pkg_map={"linux_apt": "ngspice; rm -rf /"})
    result = installer.install_tool(malicious_tool)

    assert result.status == "FAILED"
    assert "Unsafe or invalid package identifier" in result.message