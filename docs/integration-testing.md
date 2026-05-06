# v3 Integration Testing

Use `scripts/integration-test` for manual and AI-assisted live checks of real
Linux and Windows instances. Dry-run mode is safe and prints the exact commands
and manual checks. Live mode is intentionally gated by `YES=1` because it may
create billable or local VMs.

## Plan a Test

```bash
scripts/integration-test --instance linux-smoke --instance windows-smoke
scripts/integration-test --instance linux-smoke --instance windows-smoke --json
```

Recommended instance shape:

- Linux AI engineering smoke: Ubuntu provider/platform choice with
  `dev-ai` plus GUI or remote-app packages when needed.
- Windows gaming smoke: Windows GPU provider/platform choice with `gaming-streaming`
  and `desktop-streaming`.

## Run a Live Test

```bash
YES=1 scripts/integration-test --live \
  --instance linux-smoke \
  --instance windows-smoke
```

The runner performs:

1. `make instance.validate`
2. `make up`
3. `make ssh.wait`
4. `make instance.provision`
5. `make instance.status EMIT=json`
6. `make package.status` for every selected package
7. `make down` cleanup for each tested instance

It writes a JSON report under `tmp/integration-report-*.json`. Give that report
to an LLM to summarize failures, propose next commands, or compare Linux versus
Windows readiness. Use `--no-cleanup` or `EGAME_INTEGRATION_CLEANUP=0` when you
intentionally want to keep provider resources running after the test.

For temporary smoke entries, also delete the local instance registry entries:

```bash
YES=1 scripts/integration-test --live --delete-instances \
  --instance linux-smoke \
  --instance windows-smoke
```

The equivalent make target is:

```bash
YES=1 DELETE_INSTANCES=1 make integration.test INSTANCES=linux-smoke,windows-smoke
```

## Manual Checks

For Linux AI engineering environments:

- Confirm SSH command execution works.
- Confirm package status for `docker`, `dev-toolchain`, AI CLI packages, and
  remote GUI packages.
- Run a small AI/dev workflow in the VM rather than on the host.

For Windows gaming environments:

- Confirm SSH/PowerShell command execution works.
- Confirm Sunshine and RustDesk package status.
- Connect through the expected remote access path and launch a 3D app or game
  to verify smooth interaction.

The live runner destroys provider resources by default. If cleanup fails, stop
or destroy billable instances manually before continuing.
