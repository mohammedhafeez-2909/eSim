"""
Version Manager Module for eSim Automated Tool Manager.

Evaluates detected tool versions against `min_version` and `recommended_version`
thresholds defined in `config/tools.json` using PEP 440 semantic version parsing.
"""

from dataclasses import asdict, dataclass
from enum import Enum
import logging
from typing import Any, Optional

from packaging.version import InvalidVersion, Version

from modules.dependency_checker import ToolAuditResult
from modules.logger import get_app_logger


class VersionStatus(str, Enum):
    """Lifecycle compliance states for an external tool's version."""

    NOT_INSTALLED = "NOT_INSTALLED"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"
    OUTDATED_CRITICAL = "OUTDATED_CRITICAL"
    OUTDATED_RECOMMENDED = "OUTDATED_RECOMMENDED"
    UP_TO_DATE = "UP_TO_DATE"


@dataclass
class VersionAssessment:
    """Stores the semantic version evaluation and upgrade advice for one tool."""

    tool_id: str
    tool_name: str
    required: bool
    status: VersionStatus
    installed_version: Optional[str]
    min_version: str
    recommended_version: str
    upgrade_recommended: bool
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize assessment into a JSON-compatible dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data


class VersionManager:
    """
    Compares installed software versions against configurable requirements
    and produces actionable upgrade recommendations.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or get_app_logger()

    @staticmethod
    def parse_version(raw_version: Optional[str]) -> Optional[Version]:
        """
        Safely convert a version string into a `packaging.version.Version` object.
        Returns None if the string is empty or malformed.
        """
        if not raw_version:
            return None
        cleaned = raw_version.strip().lstrip("vV")
        try:
            return Version(cleaned)
        except InvalidVersion:
            return None

    def assess_tool_version(self, audit_result: ToolAuditResult) -> VersionAssessment:
        """
        Evaluate a single `ToolAuditResult` against its minimum and recommended versions.
        """
        if not audit_result.installed:
            return VersionAssessment(
                tool_id=audit_result.id,
                tool_name=audit_result.name,
                required=audit_result.required,
                status=VersionStatus.NOT_INSTALLED,
                installed_version=None,
                min_version=audit_result.min_version,
                recommended_version=audit_result.recommended_version,
                upgrade_recommended=True,
                recommendation=(
                    f"Install {audit_result.name} "
                    f"(recommended v{audit_result.recommended_version})."
                ),
            )

        installed_v = self.parse_version(audit_result.installed_version)
        min_v = self.parse_version(audit_result.min_version) or Version("0.0.0")
        rec_v = self.parse_version(audit_result.recommended_version) or min_v

        if installed_v is None:
            self.logger.warning(
                f"Unable to parse version '{audit_result.installed_version}' for {audit_result.name}"
            )
            return VersionAssessment(
                tool_id=audit_result.id,
                tool_name=audit_result.name,
                required=audit_result.required,
                status=VersionStatus.UNKNOWN_VERSION,
                installed_version=audit_result.installed_version,
                min_version=audit_result.min_version,
                recommended_version=audit_result.recommended_version,
                upgrade_recommended=False,
                recommendation=(
                    f"Verify {audit_result.name} manually; version output could not be parsed."
                ),
            )

        if installed_v < min_v:
            self.logger.warning(
                f"{audit_result.name} v{installed_v} is below minimum required v{min_v}"
            )
            return VersionAssessment(
                tool_id=audit_result.id,
                tool_name=audit_result.name,
                required=audit_result.required,
                status=VersionStatus.OUTDATED_CRITICAL,
                installed_version=str(installed_v),
                min_version=audit_result.min_version,
                recommended_version=audit_result.recommended_version,
                upgrade_recommended=True,
                recommendation=(
                    f"CRITICAL UPGRADE: {audit_result.name} v{installed_v} is below minimum "
                    f"v{min_v}. Upgrade to v{audit_result.recommended_version}."
                ),
            )

        if installed_v < rec_v:
            self.logger.info(
                f"{audit_result.name} v{installed_v} meets minimum v{min_v}, "
                f"but v{rec_v} is recommended."
            )
            return VersionAssessment(
                tool_id=audit_result.id,
                tool_name=audit_result.name,
                required=audit_result.required,
                status=VersionStatus.OUTDATED_RECOMMENDED,
                installed_version=str(installed_v),
                min_version=audit_result.min_version,
                recommended_version=audit_result.recommended_version,
                upgrade_recommended=True,
                recommendation=(
                    f"Optional upgrade: v{installed_v} is supported, "
                    f"v{audit_result.recommended_version} is recommended."
                ),
            )

        self.logger.info(f"{audit_result.name} v{installed_v} is up to date.")
        return VersionAssessment(
            tool_id=audit_result.id,
            tool_name=audit_result.name,
            required=audit_result.required,
            status=VersionStatus.UP_TO_DATE,
            installed_version=str(installed_v),
            min_version=audit_result.min_version,
            recommended_version=audit_result.recommended_version,
            upgrade_recommended=False,
            recommendation=f"{audit_result.name} v{installed_v} meets recommended standards.",
        )

    def evaluate_all(
        self, audit_results: list[ToolAuditResult]
    ) -> list[VersionAssessment]:
        """Assess versions across all scanned tools."""
        return [self.assess_tool_version(res) for res in audit_results]

    def get_outdated_tools(
        self, assessments: list[VersionAssessment]
    ) -> list[VersionAssessment]:
        """Filter tools that are critically outdated or below recommended version."""
        return [
            a
            for a in assessments
            if a.status
            in (VersionStatus.OUTDATED_CRITICAL, VersionStatus.OUTDATED_RECOMMENDED)
        ]