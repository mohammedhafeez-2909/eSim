# Automated Tool Manager for eSim

**eSim Winter Internship 2026 — Screening Task 5 (Tool Manager)**  
A modular, cross-platform Python CLI application that automates dependency detection, semantic version auditing, environment configuration validation, and safe package installation for **eSim (FOSSEE, IIT Bombay)** external EDA tools (`Ngspice`, `KiCad`, `GHDL`, `Verilator`, and `Python`).

---

## Key Features

1. **Dependency Checker (`modules/dependency_checker.py`):**
   * Scans system `PATH` for primary and fallback EDA executables (`kicad-cli` / `kicad` / `eeschema`, `ngspice` / `ngspice_con`, `ghdl`, `verilator`, `python3`).
   * Safely queries binary versions with timeout protection and regex extraction.
   * Generates structured JSON audit reports (`reports/sample_dependency_report.json`).
2. **Version Manager (`modules/version_manager.py`):**
   * Evaluates installed versions against configurable `min_version` and `recommended_version` thresholds using PEP 440 semantic versioning (`packaging`).
   * Classifies tools (`UP_TO_DATE`, `OUTDATED_RECOMMENDED`, `OUTDATED_CRITICAL`, `NOT_INSTALLED`) with clear upgrade guidance.
3. **Configuration Manager (`modules/configuration_manager.py`):**
   * Audits environment variables (`ESIM_HOME`, `PATH`), detects duplicate or non-existent `PATH` entries, and verifies binary execution permissions (`os.X_OK`).
   * Provides OS-specific remediation commands (`export` on Linux, `setx`/PowerShell on Windows).
4. **Tool Installation Manager (`modules/installation_manager.py`):**
   * Integrates with native package managers (`apt-get` / `dnf` on Linux; `winget` on Windows).
   * Enforces package identifier sanitization, explicit user confirmation before privileged installs, and a `--dry-run` simulation mode.
5. **Interactive & Non-Interactive CLI (`main.py`):**
   * Color-coded interactive terminal menu plus automation flags (`--scan`, `--dry-run`, `--export`).
6. **Activity Logger (`modules/logger.py`):**
   * Writes timestamped audit trails to rotating log files (`logs/tool_manager.log`).

---

## Project Structure

```text
eSim-Automated-Tool-Manager/
├── main.py                         # Interactive CLI & argparse entry point
├── modules/
│   ├── __init__.py
│   ├── logger.py                   # Rotating file + console activity logger
│   ├── dependency_checker.py       # Executable discovery & JSON report generator
│   ├── version_manager.py          # Semantic version comparator & upgrade advisor
│   ├── configuration_manager.py    # Environment variable, PATH & permission auditor
│   └── installation_manager.py     # Safe package installer with confirmation & dry-run
├── config/
│   └── tools.json                  # Declarative manifest of eSim tools & version rules
├── tests/
│   ├── test_logger.py
│   ├── test_dependency_checker.py
│   ├── test_version_manager.py
│   ├── test_configuration_manager.py
│   └── test_installation_manager.py
├── docs/
│   ├── architecture.md             # System architecture diagram & data flow
│   └── design_doc.md               # Design decisions, security model & resilience
├── reports/
│   └── sample_dependency_report.json
├── screenshots/                    # Terminal UI captures
├── requirements.txt
└── .gitignore