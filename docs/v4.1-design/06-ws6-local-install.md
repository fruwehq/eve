# WS6 — eve-local-install + on-instance content state (roadmap §4, §5)

## Contract changes
1. **`eve install`** (CLI): new top-level verb — equivalent to `make provision INSTANCE=<name>`.
   Runs the host-side provisioner (unchanged behavior, new ergonomic surface).
2. **`eve local install`** (CLI): new top-level verb for ON-INSTANCE execution. Reads a
   flattened step bundle + config from `$HOME/.eve/install/` and executes it via a thin
   per-OS runner. Designed for Dockerfile `RUN eve local install` or SSH invocation.
3. **On-instance runner** (`scripts/eve-local-install`): standalone Python script that:
   - Reads `steps.json` (the flattened bundle: ordered step scripts + env config)
   - Executes each step in order (bash for Linux, PowerShell for Windows)
   - Records observed content state to `state.json`
   - Re-runnable: only re-executes steps whose desired config changed (edit-config → rebuild)
4. **Step bundle flattener** (`scripts/eve-flatten-steps`): host-side script that resolves
   an instance's package provision steps, flattens them into a single JSON bundle, and
   optionally uploads to the instance.

## State model
- **Desired** (on instance): the flattened step bundle — what the host shipped.
- **Observed** (on instance): per-step status + timing — what the runner recorded.
- **Infra** (host-side): unchanged — Terraform state, instance registry.

Putting desired state ON the instance makes edit-config → rebuild first-class:
edit the desired steps on the instance, re-run `eve local install`, and it reconciles.

## Gate
- `poetry run make test` green.
- `scripts/eve-local-install --help` works.
- No golden changes.
