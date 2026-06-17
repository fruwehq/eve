# WS0 — Finish v3.5 test debt + v4.0 catalog residual

## Contract changes
1. **packages: catalog data**: The `packages:` section in `config/catalog.yaml` moves to a
   `_catalog-base/packages.yaml` in `eve-providers` (same pattern as oses/inits in Chunk D).
   `config/catalog.yaml` retains only `locations:` (removed in WS3) + `version:`. The aggregator
   already discovers `_catalog-base/*.yaml` — adding `packages.yaml` is a one-file addition.

2. **Bash test runners → Python**: The 11 `scripts/test*` bash scripts port to `#!/usr/bin/env python3`.
   Each preserves its exact checks, `[OK]/[FAIL]` output format, and exit codes. The orchestrator
   (`scripts/test`) becomes a Python script that calls the individual test scripts as subprocesses
   (the test scripts are still independent executables, just Python now).

## Approach
- Port each bash `test*` script to a Python equivalent that runs the same checks.
- For thin wrappers (test-python calls ruff+mypy+pytest, test-shellcheck calls shellcheck, etc.),
  the Python version is a thin `subprocess.run` wrapper with the same logic.
- For complex scripts (test-instances ~1500 lines, test-plugins ~1200 lines), port the logic
  faithfully. These are the hardest — they have dozens of inline checks.
- Empty the `bash shebang` allowlist section after all ports.

## Golden changes
- None from the packages: move (byte-identical aggregation).
- None from the test runner ports (same checks, same output).

## Gate
- `poetry run make test` green.
- `scripts/test-core-boundary.allowlist` bash shebang section → empty.
