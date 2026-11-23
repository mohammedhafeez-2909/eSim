"""
Unit tests for VersionManager semantic version comparisons and recommendations.
"""

from modules.dependency_checker import ToolAuditResult
from modules.version_manager import VersionManager, VersionStatus


def _make_audit_result(
    installed: bool = True,
    installed_version: str | None = "42.0",
    min_version: str = "34.0",
    recommended_version: str = "42.0",
) -> ToolAuditResult:
    return ToolAuditResult(
        id="ngspice",
        name="Ngspice Circuit Simulator",
        required=True,
        installed=installed,
        executable_used="ngspice" if installed else None,
        executable_path="/usr/bin/ngspice" if installed else None,
        installed_version=installed_version,
        min_version=min_version,
        recommended_version=recommended_version,
    )


def test_up_to_date_version() -> None:
    vm = VersionManager()
    assessment = vm.assess_tool_version(
        _make_audit_result(installed_version="43.0", min_version="34.0", recommended_version="42.0")
    )
    assert assessment.status == VersionStatus.UP_TO_DATE
    assert assessment.upgrade_recommended is False


def test_outdated_critical_version() -> None:
    vm = VersionManager()
    # Semantic comparison check: 8.0 < 34.0 (even though '8' > '3' lexicographically!)
    assessment = vm.assess_tool_version(
        _make_audit_result(installed_version="8.0", min_version="34.0", recommended_version="42.0")
    )
    assert assessment.status == VersionStatus.OUTDATED_CRITICAL
    assert assessment.upgrade_recommended is True
    assert "CRITICAL UPGRADE" in assessment.recommendation


def test_outdated_recommended_version() -> None:
    vm = VersionManager()
    assessment = vm.assess_tool_version(
        _make_audit_result(installed_version="36.0", min_version="34.0", recommended_version="42.0")
    )
    assert assessment.status == VersionStatus.OUTDATED_RECOMMENDED
    assert assessment.upgrade_recommended is True


def test_not_installed_and_unknown_version_states() -> None:
    vm = VersionManager()

    missing = vm.assess_tool_version(_make_audit_result(installed=False, installed_version=None))
    assert missing.status == VersionStatus.NOT_INSTALLED

    malformed = vm.assess_tool_version(
        _make_audit_result(installed=True, installed_version="custom-dev-build")
    )
    assert malformed.status == VersionStatus.UNKNOWN_VERSION
    assert malformed.upgrade_recommended is False


def test_get_outdated_tools_filters_properly() -> None:
    vm = VersionManager()
    results = [
        _make_audit_result(installed_version="42.0"),  # UP_TO_DATE
        _make_audit_result(installed_version="30.0"),  # OUTDATED_CRITICAL
        _make_audit_result(installed_version="38.0"),  # OUTDATED_RECOMMENDED
        _make_audit_result(installed=False, installed_version=None),  # NOT_INSTALLED
    ]
    assessments = vm.evaluate_all(results)
    outdated = vm.get_outdated_tools(assessments)
    assert len(outdated) == 2