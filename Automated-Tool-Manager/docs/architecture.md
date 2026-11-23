# System Architecture — Automated Tool Manager for eSim

## 1. High-Level Layered Architecture

The application follows a modular, layered design with strict Separation of Concerns (SoC), isolating CLI presentation from system inspection, semantic version evaluation, configuration auditing, and OS package installation.
+-------------------------------------------------------------------------+
|                       CLI Presentation Layer (main.py)                  |
|    - Interactive Menu Loop  - Colored Status Tables  - Argparse CLI     |
+------------------------------------+------------------------------------+
|
+----------------------------+----------------------------+
|                            |                            |
v                            v                            v
+------------------+      +---------------------+      +-------------------+
| DependencyChecker|      |   VersionManager    |      | ConfigurationMgr  |
| - PATH lookup    |      | - PEP 440 parsing   |      | - Env var check   |
| - Safe subprocess|      | - Min/Rec thresholds|      | - PATH hygiene    |
| - JSON reporting |      | - Upgrade advisor   |      | - Exec permissions|
+--------+---------+      +----------+----------+      +---------+---------+
|                           |                           |
+---------------------------+---------------------------+
|
v
+-------------------------------+
|      InstallationManager      |
| - OS Package Strategy         |
|   (Linux apt/dnf, Win winget) |
| - Regex Package Sanitizer     |
| - Confirmation Guardrail      |
| - Dry-Run Simulation Engine   |
+---------------+---------------+
|
+----------------------------+----------------------------+
|                                                         |
v                                                         v
+------------------+                                   +--------------------+
|  ActivityLogger  |                                   |  config/tools.json |
| - Rotating logs  |                                   | - Tool definitions |
| - Audit trail    |                                   | - Version rules    |
+------------------+                                   +--------------------+

## 2. Core Data Flow

1. **Manifest Ingestion:** `DependencyChecker` parses `config/tools.json` into validated tool specifications.
2. **System Audit:** `DependencyChecker` resolves primary and fallback executables (`shutil.which`) and runs `<binary> --version` via `subprocess.run(..., shell=False, timeout=5)`, emitting typed `ToolAuditResult` dataclasses.
3. **Version Lifecycle Classification:** `VersionManager` consumes `ToolAuditResult` objects and classifies each tool into `UP_TO_DATE`, `OUTDATED_RECOMMENDED`, `OUTDATED_CRITICAL`, `NOT_INSTALLED`, or `UNKNOWN_VERSION`.
4. **Environment & Permission Validation:** `ConfigurationManager` inspects `ESIM_HOME`, system `PATH` integrity, and binary execution permissions (`os.access(..., os.X_OK)`), producing actionable OS-specific remediation commands.
5. **Guarded Provisioning:** `InstallationManager` maps missing/outdated tools to native OS package managers, enforces package-name sanitization (`^[a-zA-Z0-9._+-]+$`), requires explicit user confirmation, and supports `--dry-run` simulation.
6. **Observability:** Every module logs structured diagnostic and audit events to `logs/tool_manager.log` via `ActivityLogger`.