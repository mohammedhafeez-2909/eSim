"""
Tool Installation Manager Module for eSim Automated Tool Manager.

Automates installation and upgrading of missing or outdated eSim dependencies
across Linux (`apt`, `dnf`) and Windows (`winget`) with mandatory user
confirmation guardrails, command sanitization, and dry-run support.
"""

from dataclasses import asdict, dataclass
import logging
import platform
import re
import shutil
import subprocess
from typing import Callable, Optional

from modules.dependency_checker import ToolAuditResult
from modules.logger import get_app_logger

# Strict allowlist for package identifiers (prevents command/flag injection)
SAFE_PACKAGE_PATTERN = re.compile(r"^[a-zA-Z0-9._+-]+$")


@dataclass
class InstallationResult:
    """Represents the outcome of a single tool installation attempt."""

    tool_id: str
    tool_name: str
    package_manager: Optional[str]
    package_name: Optional[str]
    command: list[str]
    status: str  # "INSTALLED", "DRY_RUN", "CANCELLED", "UNSUPPORTED", "FAILED"
    message: str
    return_code: Optional[int] = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class InstallationManager:
    """
    Safely installs or upgrades external EDA tools using native OS package managers.
    """

    def __init__(
        self,
        dry_run: bool = False,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.dry_run = dry_run
        self.confirm_callback = confirm_callback or self._default_cli_confirm
        self.logger = logger or get_app_logger()
        self.host_os = platform.system()

    @staticmethod
    def _default_cli_confirm(prompt_message: str) -> bool:
        """Default interactive terminal confirmation prompt."""
        reply = input(f"{prompt_message} [y/N]: ").strip().lower()
        return reply in ("y", "yes")

    def detect_package_manager(self) -> Optional[tuple[str, str]]:
        """
        Detect the active OS package manager and return `(config_key, binary_name)`.
        Prioritizes Linux (`apt`, `dnf`) while supporting Windows (`winget`).
        """
        if self.host_os == "Linux":
            if shutil.which("apt-get") or shutil.which("apt"):
                return ("linux_apt", "apt-get")
            if shutil.which("dnf"):
                return ("linux_dnf", "dnf")
        elif self.host_os == "Windows":
            if shutil.which("winget"):
                return ("windows_winget", "winget")
        return None

    def build_install_command(
        self, pkg_key: str, pkg_binary: str, package_name: str
    ) -> list[str]:
        """
        Validate package identifier and construct a safe argument list (no shell=True).
        """
        if not package_name or not SAFE_PACKAGE_PATTERN.match(package_name):
            raise ValueError(f"Unsafe or invalid package identifier: '{package_name}'")

        if pkg_key == "linux_apt":
            return ["sudo", pkg_binary, "install", "-y", package_name]
        if pkg_key == "linux_dnf":
            return ["sudo", pkg_binary, "install", "-y", package_name]
        if pkg_key == "windows_winget":
            return [
                pkg_binary,
                "install",
                "--id",
                package_name,
                "-e",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ]
        raise ValueError(f"Unsupported package manager key: '{pkg_key}'")

    def install_tool(
        self,
        tool_audit: ToolAuditResult,
        dry_run: Optional[bool] = None,
    ) -> InstallationResult:
        """
        Install a single missing or outdated tool after explicit user confirmation.
        """
        effective_dry_run = self.dry_run if dry_run is None else dry_run
        pm_info = self.detect_package_manager()

        if not pm_info:
            msg = f"No supported package manager detected on {self.host_os}."
            self.logger.error(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=None,
                package_name=None,
                command=[],
                status="UNSUPPORTED",
                message=msg,
            )

        pkg_key, pkg_binary = pm_info
        package_name = tool_audit.packages.get(pkg_key)
        if not package_name:
            msg = f"No '{pkg_key}' package mapping defined for {tool_audit.name}."
            self.logger.warning(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=None,
                command=[],
                status="UNSUPPORTED",
                message=msg,
            )

        try:
            cmd = self.build_install_command(pkg_key, pkg_binary, package_name)
        except ValueError as exc:
            self.logger.error(f"Blocked invalid installation command: {exc}")
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=[],
                status="FAILED",
                message=str(exc),
            )

        cmd_display = " ".join(cmd)

        if effective_dry_run:
            msg = f"[DRY-RUN] Would execute: {cmd_display}"
            self.logger.info(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=cmd,
                status="DRY_RUN",
                message=msg,
                return_code=0,
            )

        # Mandatory security guardrail: ask explicit confirmation before privileged execution
        confirmed = self.confirm_callback(
            f"Install {tool_audit.name} using `{cmd_display}`?"
        )
        if not confirmed:
            msg = f"User declined installation of {tool_audit.name}."
            self.logger.warning(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=cmd,
                status="CANCELLED",
                message=msg,
            )

        self.logger.info(f"Executing installation command: {cmd_display}")
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                shell=False,
            )
            if completed.returncode == 0:
                msg = f"Successfully installed {tool_audit.name} ({package_name})."
                self.logger.info(msg)
                return InstallationResult(
                    tool_id=tool_audit.id,
                    tool_name=tool_audit.name,
                    package_manager=pkg_binary,
                    package_name=package_name,
                    command=cmd,
                    status="INSTALLED",
                    message=msg,
                    return_code=0,
                )

            stderr_snippet = (completed.stderr or completed.stdout).strip()[:200]
            msg = f"Installation failed (exit code {completed.returncode}): {stderr_snippet}"
            self.logger.error(f"{tool_audit.name}: {msg}")
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=cmd,
                status="FAILED",
                message=msg,
                return_code=completed.returncode,
            )
        except subprocess.TimeoutExpired:
            msg = f"Installation of {tool_audit.name} timed out after 300s."
            self.logger.error(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=cmd,
                status="FAILED",
                message=msg,
            )
        except OSError as exc:
            msg = f"OS error running installer for {tool_audit.name}: {exc}"
            self.logger.error(msg)
            return InstallationResult(
                tool_id=tool_audit.id,
                tool_name=tool_audit.name,
                package_manager=pkg_binary,
                package_name=package_name,
                command=cmd,
                status="FAILED",
                message=msg,
            )

    def install_missing_tools(
        self,
        audit_results: list[ToolAuditResult],
        include_optional: bool = False,
        dry_run: Optional[bool] = None,
    ) -> list[InstallationResult]:
        """Batch-install missing required (and optionally optional) tools."""
        targets = [
            t
            for t in audit_results
            if not t.installed and (t.required or include_optional)
        ]
        return [self.install_tool(tool, dry_run=dry_run) for tool in targets]