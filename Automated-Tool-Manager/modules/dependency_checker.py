"""
Dependency Checker Module for eSim Automated Tool Manager.

Scans the host environment for external EDA tools defined in `config/tools.json`,
verifies executable availability in system PATH, extracts installed versions
safely using subprocess, and generates structured dependency audit reports.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Optional

from modules.logger import get_app_logger


@dataclass
class ToolAuditResult:
    """Represents the inspection outcome for a single external tool."""

    id: str
    name: str
    required: bool
    installed: bool
    executable_used: Optional[str] = None
    executable_path: Optional[str] = None
    installed_version: Optional[str] = None
    min_version: str = "0.0.0"
    recommended_version: str = "0.0.0"
    packages: dict[str, str] = field(default_factory=dict)
    description: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize audit result into a JSON-compatible dictionary."""
        return asdict(self)


class DependencyChecker:
    """
    Audits system dependencies required by eSim based on a JSON manifest.
    """

    def __init__(
        self,
        config_path: str = "config/tools.json",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.logger = logger or get_app_logger()
        self.config_data: dict[str, Any] = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load and validate the tools JSON configuration file."""
        if not self.config_path.exists():
            self.logger.error(f"Configuration file not found: {self.config_path}")
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if "tools" not in data or not isinstance(data["tools"], list):
                raise ValueError("Invalid config schema: missing 'tools' list.")
            self.logger.debug(f"Loaded {len(data['tools'])} tool definitions from {self.config_path}")
            return data
        except json.JSONDecodeError as exc:
            self.logger.error(f"Malformed JSON in {self.config_path}: {exc}")
            raise

    def find_executable(
        self, primary_exec: str, alt_execs: Optional[list[str]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve the first available binary in PATH from primary and fallback names.

        Returns:
            Tuple of (matched_executable_name, full_resolved_path) or (None, None).
        """
        candidates = [primary_exec] + (alt_execs or [])
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return candidate, str(Path(resolved).resolve())
        return None, None

    def get_tool_version(
        self, executable_path: str, version_flag: str, version_regex: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Execute `<executable> <version_flag>` safely and parse semantic version.

        Returns:
            Tuple of (parsed_version_string, error_message_if_any).
        """
        cmd = [executable_path, version_flag]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                shell=False,
            )
            # Some CLI tools (like java or older ngspice) output version to stderr
            combined_output = f"{completed.stdout}\n{completed.stderr}".strip()
            match = re.search(version_regex, combined_output, re.IGNORECASE)
            if match:
                return match.group(1), None

            self.logger.warning(
                f"Could not parse version for '{executable_path}' from output: {combined_output[:120]}"
            )
            return None, "Version pattern not matched in tool output"
        except subprocess.TimeoutExpired:
            msg = f"Timed out while querying version for '{executable_path}'"
            self.logger.error(msg)
            return None, msg
        except OSError as exc:
            msg = f"OS error executing '{executable_path}': {exc}"
            self.logger.error(msg)
            return None, msg

    def check_single_tool(self, tool_spec: dict[str, Any]) -> ToolAuditResult:
        """Inspect a single tool entry from `tools.json`."""
        tool_id = tool_spec["id"]
        name = tool_spec["name"]
        primary_exec = tool_spec["executable"]
        alt_execs = tool_spec.get("alt_executables", [])

        matched_exec, resolved_path = self.find_executable(primary_exec, alt_execs)

        if not resolved_path:
            level = logging.ERROR if tool_spec.get("required", False) else logging.WARNING
            self.logger.log(level, f"Missing tool: {name} (searched: {[primary_exec] + alt_execs})")
            return ToolAuditResult(
                id=tool_id,
                name=name,
                required=tool_spec.get("required", False),
                installed=False,
                min_version=tool_spec.get("min_version", "0.0.0"),
                recommended_version=tool_spec.get("recommended_version", "0.0.0"),
                packages=tool_spec.get("packages", {}),
                description=tool_spec.get("description", ""),
            )

        version, err = self.get_tool_version(
            resolved_path,
            tool_spec.get("version_flag", "--version"),
            tool_spec.get("version_regex", r"(\d+\.\d+\.\d+)"),
        )
        self.logger.info(
            f"Detected {name}: path={resolved_path}, version={version or 'unknown'}"
        )
        return ToolAuditResult(
            id=tool_id,
            name=name,
            required=tool_spec.get("required", False),
            installed=True,
            executable_used=matched_exec,
            executable_path=resolved_path,
            installed_version=version,
            min_version=tool_spec.get("min_version", "0.0.0"),
            recommended_version=tool_spec.get("recommended_version", "0.0.0"),
            packages=tool_spec.get("packages", {}),
            description=tool_spec.get("description", ""),
            error=err,
        )

    def check_all_dependencies(self) -> list[ToolAuditResult]:
        """Run dependency checks across all tools defined in the manifest."""
        self.logger.info("Starting full eSim dependency scan...")
        results = [self.check_single_tool(tool) for tool in self.config_data["tools"]]
        installed_count = sum(1 for r in results if r.installed)
        self.logger.info(
            f"Dependency scan finished: {installed_count}/{len(results)} tools detected."
        )
        return results

    def generate_report(
        self,
        results: Optional[list[ToolAuditResult]] = None,
        export_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build a structured summary report and optionally write it to a JSON file.
        """
        audit_results = results if results is not None else self.check_all_dependencies()
        missing_required = [
            r.name for r in audit_results if not r.installed and r.required
        ]
        missing_optional = [
            r.name for r in audit_results if not r.installed and not r.required
        ]

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "host_os": platform.system(),
            "host_release": platform.release(),
            "python_runtime": platform.python_version(),
            "summary": {
                "total_tools": len(audit_results),
                "installed_count": sum(1 for r in audit_results if r.installed),
                "missing_required_count": len(missing_required),
                "missing_optional_count": len(missing_optional),
                "missing_required": missing_required,
                "missing_optional": missing_optional,
                "ready_for_esim": len(missing_required) == 0,
            },
            "tools": [r.to_dict() for r in audit_results],
        }

        if export_path:
            out_file = Path(export_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with out_file.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            self.logger.info(f"Dependency report exported to {out_file}")

        return report