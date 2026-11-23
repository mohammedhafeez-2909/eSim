"""
Configuration Manager Module for eSim Automated Tool Manager.

Validates system environment variables, verifies PATH integrity, checks binary
execution permissions, and generates OS-aware configuration recommendations.
"""

from dataclasses import asdict, dataclass, field
import logging
import os
from pathlib import Path
import platform
from typing import Any, Optional

from modules.dependency_checker import ToolAuditResult
from modules.logger import get_app_logger


@dataclass
class ConfigIssue:
    """Represents a single environment or path configuration finding."""

    category: str  # "ENV_VAR", "PATH", "EXECUTABLE_PERM"
    severity: str  # "ERROR", "WARNING", "INFO"
    target: str
    message: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfigurationReport:
    """Aggregated outcome of environment and executable configuration checks."""

    host_os: str
    is_valid: bool
    checked_env_vars: dict[str, Optional[str]]
    issues: list[ConfigIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_os": self.host_os,
            "is_valid": self.is_valid,
            "checked_env_vars": self.checked_env_vars,
            "issue_count": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class ConfigurationManager:
    """
    Audits system paths, environment variables, and tool binary permissions.
    """

    def __init__(
        self,
        env_specs: Optional[list[dict[str, Any]]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.env_specs = env_specs or [
            {"name": "ESIM_HOME", "required": False, "description": "eSim root directory"},
            {"name": "PATH", "required": True, "description": "System executable search path"},
        ]
        self.logger = logger or get_app_logger()
        self.host_os = platform.system()

    def _format_env_suggestion(self, var_name: str, example_value: str) -> str:
        """Return an OS-appropriate command to set an environment variable."""
        if self.host_os == "Windows":
            return f'setx {var_name} "{example_value}"  (or in PowerShell: $env:{var_name}="{example_value}")'
        return f'export {var_name}="{example_value}"  (add to ~/.bashrc or ~/.zshrc)'

    def check_environment_variables(self) -> tuple[dict[str, Optional[str]], list[ConfigIssue]]:
        """Validate required and optional environment variables from config."""
        checked: dict[str, Optional[str]] = {}
        issues: list[ConfigIssue] = []

        for spec in self.env_specs:
            var_name = spec["name"]
            required = spec.get("required", False)
            val = os.environ.get(var_name)
            checked[var_name] = val

            if not val or not val.strip():
                severity = "ERROR" if required else "WARNING"
                default_hint = (
                    r"C:\FOSSEE\eSim" if self.host_os == "Windows" else "/opt/eSim"
                )
                issues.append(
                    ConfigIssue(
                        category="ENV_VAR",
                        severity=severity,
                        target=var_name,
                        message=f"Environment variable '{var_name}' is not set.",
                        recommendation=self._format_env_suggestion(var_name, default_hint),
                    )
                )
                self.logger.log(
                    logging.ERROR if required else logging.WARNING,
                    f"Environment variable '{var_name}' is unset (required={required}).",
                )
            elif var_name.endswith("_HOME") or var_name.endswith("_DIR"):
                # Verify directory-based env vars actually exist on disk
                if not Path(val).exists():
                    issues.append(
                        ConfigIssue(
                            category="ENV_VAR",
                            severity="ERROR",
                            target=var_name,
                            message=f"'{var_name}' points to a non-existent path: {val}",
                            recommendation=f"Verify the installation path and update {var_name}.",
                        )
                    )
                    self.logger.error(f"Invalid path in {var_name}: {val}")

        return checked, issues

    def check_system_path(self) -> list[ConfigIssue]:
        """Inspect PATH entries for missing directories or duplicates."""
        issues: list[ConfigIssue] = []
        raw_path = os.environ.get("PATH", "")
        if not raw_path.strip():
            issues.append(
                ConfigIssue(
                    category="PATH",
                    severity="ERROR",
                    target="PATH",
                    message="System PATH is completely empty.",
                    recommendation="Restore default system PATH variables immediately.",
                )
            )
            return issues

        entries = [p for p in raw_path.split(os.pathsep) if p.strip()]
        seen: set[str] = set()
        duplicate_count = 0
        missing_dirs: list[str] = []

        for entry in entries:
            norm = os.path.normcase(os.path.normpath(entry))
            if norm in seen:
                duplicate_count += 1
            else:
                seen.add(norm)
                if not Path(entry).exists():
                    missing_dirs.append(entry)

        if duplicate_count > 0:
            issues.append(
                ConfigIssue(
                    category="PATH",
                    severity="INFO",
                    target="PATH",
                    message=f"Detected {duplicate_count} duplicate entries in system PATH.",
                    recommendation="Clean up redundant PATH entries to speed up binary lookups.",
                )
            )

        if missing_dirs:
            sample = ", ".join(missing_dirs[:3])
            issues.append(
                ConfigIssue(
                    category="PATH",
                    severity="WARNING",
                    target="PATH",
                    message=f"{len(missing_dirs)} PATH entries do not exist on disk (e.g., {sample}).",
                    recommendation="Remove stale directories from PATH to prevent broken tool resolution.",
                )
            )
            self.logger.debug(f"Stale PATH directories detected: {missing_dirs}")

        return issues

    def verify_tool_executables(
        self, audit_results: list[ToolAuditResult]
    ) -> list[ConfigIssue]:
        """Verify each installed tool binary exists as a file and is executable."""
        issues: list[ConfigIssue] = []

        for tool in audit_results:
            if not tool.installed or not tool.executable_path:
                continue

            bin_path = Path(tool.executable_path)
            if not bin_path.exists() or not bin_path.is_file():
                issues.append(
                    ConfigIssue(
                        category="EXECUTABLE_PERM",
                        severity="ERROR",
                        target=tool.name,
                        message=f"Resolved binary path is invalid or broken symlink: {bin_path}",
                        recommendation=f"Reinstall {tool.name} or fix symlink at {bin_path}.",
                    )
                )
                self.logger.error(f"Broken binary path for {tool.name}: {bin_path}")
            elif not os.access(bin_path, os.X_OK):
                fix_cmd = (
                    f"chmod +x {bin_path}"
                    if self.host_os != "Windows"
                    else f"Check file permissions on {bin_path}"
                )
                issues.append(
                    ConfigIssue(
                        category="EXECUTABLE_PERM",
                        severity="ERROR",
                        target=tool.name,
                        message=f"Binary '{bin_path}' lacks execute permission.",
                        recommendation=f"Grant execute permissions: {fix_cmd}",
                    )
                )
                self.logger.error(f"Binary lacks execute permissions: {bin_path}")

        return issues

    def run_full_check(
        self, audit_results: Optional[list[ToolAuditResult]] = None
    ) -> ConfigurationReport:
        """Execute all environment, PATH, and binary permission checks."""
        self.logger.info("Running system configuration and environment audit...")
        checked_vars, env_issues = self.check_environment_variables()
        path_issues = self.check_system_path()
        exec_issues = (
            self.verify_tool_executables(audit_results) if audit_results else []
        )

        all_issues = env_issues + path_issues + exec_issues
        has_errors = any(issue.severity == "ERROR" for issue in all_issues)

        report = ConfigurationReport(
            host_os=self.host_os,
            is_valid=not has_errors,
            checked_env_vars=checked_vars,
            issues=all_issues,
        )
        self.logger.info(
            f"Configuration audit complete: valid={report.is_valid}, issues={len(all_issues)}"
        )
        return report