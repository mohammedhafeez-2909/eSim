"""
Main Entry Point & Interactive CLI for eSim Automated Tool Manager.

Integrates DependencyChecker, VersionManager, ConfigurationManager,
InstallationManager, and ActivityLogger into a cohesive, user-friendly
terminal application with both interactive menu mode and CLI flags.
"""

import argparse
from datetime import datetime
from pathlib import Path
import platform
import sys
from typing import Optional

from colorama import Fore, Style, init

from modules.configuration_manager import ConfigurationManager
from modules.dependency_checker import DependencyChecker, ToolAuditResult
from modules.installation_manager import InstallationManager
from modules.logger import ActivityLogger
from modules.version_manager import VersionManager, VersionStatus

# Initialize cross-platform ANSI colors (Windows + Linux)
init(autoreset=True)


class ToolManagerCLI:
    """Interactive command-line controller for the eSim Automated Tool Manager."""

    def __init__(self, config_path: str = "config/tools.json") -> None:
        self.activity_logger = ActivityLogger()
        self.logger = self.activity_logger.get_logger()
        self.checker = DependencyChecker(config_path=config_path, logger=self.logger)
        self.version_manager = VersionManager(logger=self.logger)
        self.config_manager = ConfigurationManager(
            env_specs=self.checker.config_data.get("environment_variables"),
            logger=self.logger,
        )
        self.installer = InstallationManager(dry_run=False, logger=self.logger)
        self._cached_results: Optional[list[ToolAuditResult]] = None

    def _get_audit_results(self, force_refresh: bool = False) -> list[ToolAuditResult]:
        if self._cached_results is None or force_refresh:
            self._cached_results = self.checker.check_all_dependencies()
        return self._cached_results

    @staticmethod
    def print_banner() -> None:
        line = "=" * 72
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{line}")
        print("   eSim Automated Tool Manager  |  FOSSEE eSim Internship Task 5")
        print(f"   Host OS: {platform.system()} ({platform.release()})  |  Python: {platform.python_version()}")
        print(f"{line}{Style.RESET_ALL}")

    def display_dependency_scan(self, force_refresh: bool = True) -> None:
        """Run and render a formatted table of all eSim dependencies."""
        print(f"\n{Fore.CYAN}>>> Scanning eSim External Tools & Dependencies...{Style.RESET_ALL}")
        results = self._get_audit_results(force_refresh=force_refresh)

        header = f"{'TOOL NAME':<28} {'TIER':<10} {'STATUS':<12} {'VERSION':<12} {'EXECUTABLE PATH'}"
        print(f"\n{Style.BRIGHT}{header}{Style.RESET_ALL}")
        print("-" * 92)

        for r in results:
            tier = "Required" if r.required else "Optional"
            if r.installed:
                status_badge = f"{Fore.GREEN}INSTALLED{Style.RESET_ALL}   "
                ver_str = r.installed_version or "unknown"
                path_str = r.executable_path or "-"
            else:
                color = Fore.RED if r.required else Fore.YELLOW
                status_badge = f"{color}MISSING{Style.RESET_ALL}     "
                ver_str = "-"
                path_str = "Not found in PATH"

            print(f"{r.name:<28} {tier:<10} {status_badge} {ver_str:<12} {path_str}")

        installed_cnt = sum(1 for r in results if r.installed)
        missing_req = [r.name for r in results if not r.installed and r.required]
        print("-" * 92)
        print(f"Summary: {installed_cnt}/{len(results)} tools detected.")
        if missing_req:
            print(f"{Fore.RED}Action Needed: Missing required tools -> {', '.join(missing_req)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}All required eSim dependencies are installed!{Style.RESET_ALL}")

    def display_version_report(self) -> None:
        """Evaluate installed versions against min/recommended thresholds."""
        print(f"\n{Fore.CYAN}>>> Evaluating Tool Versions & Upgrade Recommendations...{Style.RESET_ALL}")
        results = self._get_audit_results(force_refresh=False)
        assessments = self.version_manager.evaluate_all(results)

        for a in assessments:
            if a.status == VersionStatus.UP_TO_DATE:
                badge = f"{Fore.GREEN}[UP TO DATE]{Style.RESET_ALL}"
            elif a.status == VersionStatus.OUTDATED_RECOMMENDED:
                badge = f"{Fore.YELLOW}[UPDATE AVAIL]{Style.RESET_ALL}"
            elif a.status == VersionStatus.OUTDATED_CRITICAL:
                badge = f"{Fore.RED}[OUTDATED]{Style.RESET_ALL}"
            elif a.status == VersionStatus.NOT_INSTALLED:
                badge = f"{Fore.RED}[MISSING]{Style.RESET_ALL}"
            else:
                badge = f"{Fore.MAGENTA}[UNKNOWN]{Style.RESET_ALL}"

            cur = a.installed_version or "N/A"
            print(
                f"  {badge} {a.tool_name:<26} | Installed: {cur:<8} | "
                f"Min: {a.min_version:<7} | Rec: {a.recommended_version}"
            )
            print(f"       -> {a.recommendation}")

    def display_configuration_audit(self) -> None:
        """Check environment variables, PATH entries, and binary permissions."""
        print(f"\n{Fore.CYAN}>>> Auditing Environment Variables & Path Configuration...{Style.RESET_ALL}")
        results = self._get_audit_results(force_refresh=False)
        report = self.config_manager.run_full_check(audit_results=results)

        print("\nChecked Environment Variables:")
        for var, val in report.checked_env_vars.items():
            display_val = val if val else f"{Fore.YELLOW}<NOT SET>{Style.RESET_ALL}"
            if var == "PATH" and val:
                display_val = f"<SET ({len(val.split(';')) if platform.system() == 'Windows' else len(val.split(':'))} entries)>"
            print(f"  - {var}: {display_val}")

        if not report.issues:
            print(f"\n{Fore.GREEN}No configuration issues detected.{Style.RESET_ALL}")
            return

        print(f"\nConfiguration Findings ({len(report.issues)}):")
        for issue in report.issues:
            color = (
                Fore.RED
                if issue.severity == "ERROR"
                else Fore.YELLOW
                if issue.severity == "WARNING"
                else Fore.CYAN
            )
            print(f"  {color}[{issue.severity}]{Style.RESET_ALL} ({issue.category}) {issue.message}")
            print(f"       Fix: {issue.recommendation}")

    def run_installation_workflow(self, dry_run: bool = False) -> None:
        """Install missing required tools (or simulate in dry-run mode)."""
        mode_label = "DRY-RUN SIMULATION" if dry_run else "LIVE INSTALLATION"
        print(f"\n{Fore.CYAN}>>> Starting Tool Installation Workflow ({mode_label})...{Style.RESET_ALL}")

        results = self._get_audit_results(force_refresh=True)
        missing = [r for r in results if not r.installed]
        if not missing:
            print(f"{Fore.GREEN}All tools in manifest are already installed!{Style.RESET_ALL}")
            return

        include_opt = False
        optional_missing = [r for r in missing if not r.required]
        if optional_missing:
            ans = input(
                f"Include {len(optional_missing)} optional HDL tools ({', '.join(t.id for t in optional_missing)})? [y/N]: "
            ).strip().lower()
            include_opt = ans in ("y", "yes")

        outcomes = self.installer.install_missing_tools(
            results, include_optional=include_opt, dry_run=dry_run
        )
        if not outcomes:
            print(f"{Fore.YELLOW}No tools selected for installation.{Style.RESET_ALL}")
            return

        print("\nInstallation Summary:")
        for out in outcomes:
            color = (
                Fore.GREEN
                if out.status in ("INSTALLED", "DRY_RUN")
                else Fore.YELLOW
                if out.status == "CANCELLED"
                else Fore.RED
            )
            print(f"  {color}[{out.status}]{Style.RESET_ALL} {out.tool_name}: {out.message}")

        if not dry_run:
            self._get_audit_results(force_refresh=True)

    def export_json_report(self, custom_path: Optional[str] = None) -> Path:
        """Generate and save a JSON dependency report in `reports/`."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = custom_path or f"reports/dependency_report_{timestamp}.json"
        results = self._get_audit_results(force_refresh=False)
        self.checker.generate_report(results=results, export_path=target)
        out_path = Path(target)
        print(f"\n{Fore.GREEN}Dependency report successfully saved to: {out_path.resolve()}{Style.RESET_ALL}")
        return out_path

    def view_activity_logs(self, lines: int = 15) -> None:
        """Print recent entries from the activity log file."""
        print(f"\n{Fore.CYAN}>>> Recent Activity Logs (last {lines} entries):{Style.RESET_ALL}")
        entries = self.activity_logger.read_recent_logs(lines=lines)
        if not entries:
            print("  No log entries found.")
            return
        for entry in entries:
            print(f"  {entry}")

    def run_interactive_menu(self) -> None:
        """Launch the interactive CLI loop."""
        self.print_banner()
        while True:
            print(f"\n{Style.BRIGHT}Main Menu:{Style.RESET_ALL}")
            print("  [1] Scan Dependencies & Check Installed Tools")
            print("  [2] Check Tool Versions & Upgrade Recommendations")
            print("  [3] Audit Environment Variables & Path Configuration")
            print("  [4] Install Missing Tools (With Confirmation)")
            print("  [5] Simulate Tool Installation (Dry-Run Mode)")
            print("  [6] Export Dependency Report (JSON)")
            print("  [7] View Activity Logs")
            print("  [0] Exit")

            choice = input("\nSelect an option [0-7]: ").strip()

            if choice == "1":
                self.display_dependency_scan(force_refresh=True)
            elif choice == "2":
                self.display_version_report()
            elif choice == "3":
                self.display_configuration_audit()
            elif choice == "4":
                self.run_installation_workflow(dry_run=False)
            elif choice == "5":
                self.run_installation_workflow(dry_run=True)
            elif choice == "6":
                self.export_json_report()
            elif choice == "7":
                self.view_activity_logs()
            elif choice == "0":
                print(f"\n{Fore.CYAN}Exiting eSim Automated Tool Manager. Goodbye!{Style.RESET_ALL}")
                break
            else:
                print(f"{Fore.RED}Invalid selection '{choice}'. Please enter a number between 0 and 7.{Style.RESET_ALL}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated Tool Manager for eSim (Dependency, Version, Config & Installer CLI)"
    )
    parser.add_argument(
        "--config", default="config/tools.json", help="Path to tools JSON configuration"
    )
    parser.add_argument(
        "--scan", action="store_true", help="Run dependency scan and exit"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate missing tool installation and exit"
    )
    parser.add_argument(
        "--export", metavar="PATH", help="Export JSON dependency report to PATH and exit"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        cli = ToolManagerCLI(config_path=args.config)
    except Exception as exc:
        print(f"{Fore.RED}[FATAL] Failed to initialize Tool Manager: {exc}{Style.RESET_ALL}", file=sys.stderr)
        return 1

    if args.scan or args.dry_run or args.export:
        cli.print_banner()
        if args.scan:
            cli.display_dependency_scan(force_refresh=True)
            cli.display_version_report()
            cli.display_configuration_audit()
        if args.dry_run:
            cli.run_installation_workflow(dry_run=True)
        if args.export:
            cli.export_json_report(custom_path=args.export)
        return 0

    try:
        cli.run_interactive_menu()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user. Exiting cleanly.{Style.RESET_ALL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())