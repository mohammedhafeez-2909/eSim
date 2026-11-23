# Technical Design Document — eSim Automated Tool Manager

## 1. Design Goals & Engineering Principles
* **Declarative Configuration over Hardcoding:** All external tool metadata (`ngspice`, `kicad`, `ghdl`, `verilator`, `python3`), regex extractors, version floors, and OS package identifiers live in `config/tools.json`. Adding new EDA tools requires zero Python code changes.
* **Linux-First, Cross-Platform Extensible:** Package detection prioritizes Linux (`apt-get`/`apt` and `dnf`) while cleanly abstracting Windows (`winget`) via `platform.system()` and `pathlib.Path`.
* **Security-First Subprocess Execution:**
  * Every external command executes with `shell=False` and an explicit argument list (`list[str]`).
  * Package identifiers are validated against `^[a-zA-Z0-9._+-]+$` before constructing installation commands.
  * Privileged commands (`sudo apt-get install -y ...`) are gated behind an explicit confirmation callback and can be previewed safely via `--dry-run`.
* **PEP 440 Semantic Versioning:** Uses PyPA's `packaging.version.Version` rather than fragile string comparisons so multi-digit versions (`34.0` vs `8.0`) compare accurately.

## 2. Error Handling & Resilience Strategy
| Failure Scenario | Handling Mechanism |
| :--- | :--- |
| Missing or malformed `config/tools.json` | Raises `FileNotFoundError` / `json.JSONDecodeError` early with descriptive error logs. |
| Hanging tool `--version` command | Enforces `timeout=5` on `subprocess.run` and catches `subprocess.TimeoutExpired` gracefully. |
| Unparseable version output | Classifies tool as `UNKNOWN_VERSION` without crashing the audit pipeline. |
| Package installation failure / user decline | Captures non-zero exit codes, `stderr`, and user cancellations into structured `InstallationResult` objects. |
| Windows file locks on rotated logs | `ActivityLogger.close()` cleanly closes and detaches handlers before cleanup. |

## 3. Verification & Testing Strategy
All modules are covered by automated `pytest` suites (`tests/`) utilizing `monkeypatch` and `tmp_path` so tests run deterministically in <0.5s without modifying the host OS or installing packages.