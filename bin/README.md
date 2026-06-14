# bin/ — env-bootstrap launchers (intentionally shell, intentionally not in scripts/)

These are the **env-bootstrap layer**: they run *before* (and in order to invoke)
the poetry-managed Python environment, so they cannot themselves be poetry-run
Python entrypoints. They are the explicit, justified permanent exception to the
"`scripts/` is Python-only" invariant (v4.0 Phase 2): rather than carry a growing
bash allowlist inside `scripts/`, the bootstrap shims live here, out of the
`core-boundary` scan.

- **`eve`** — the user launcher: `cd` to the repo root and `exec poetry run python
  scripts/eve-tui`. (`scripts/eve-tui` is the real TUI entrypoint and *does* run
  under poetry, so it stays in `scripts/`.)

Everything that runs *after* the environment is up belongs in `scripts/` as Python.
