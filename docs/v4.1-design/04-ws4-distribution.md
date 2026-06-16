# WS4 — Distribution / zero-setup

## Contract changes
1. `pyproject.toml` gains `[project.scripts]` with `eve = "eve_sdk.cli:main"` — a
   console entry point that `pipx install .` exposes as the `eve` command.
2. `package-mode` switches to `true` so poetry builds an installable wheel.
3. `eve_sdk/cli.py` (new, thin) delegates to `scripts/eve-cli:main()` so the CLI
   tree stays in scripts/ while the entry point is importable from the installed package.
4. A Homebrew formula template documents the macOS install path (`brew install fruwehq/tap/eve`).
   The actual tap repo (`homebrew-eve`) is created by the user when publishing.

## Approach
- `eve_sdk/cli.py` is a 10-line shim: insert repo root on sys.path, run scripts/eve-cli's main().
- `pyproject.toml`: add scripts + package-mode + include eve_sdk.
- No behavior change — the CLI is identical; only the install surface changes.

## Gate
- `pipx install .` exposes `eve` (verified manually).
- `poetry run make test` green (no test changes — the CLI shim is additive).
