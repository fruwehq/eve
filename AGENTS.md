# Agent / AI Contributor Guidelines

## Configuration and defaults

**All configurable defaults live in `.env`.** Never use shell `${VAR:-default}` to encode a meaningful default inside a script. If a variable needs a default, declare it (commented or uncommented) in `.env` so it is discoverable in one place.

- User-specific overrides go in `.env.local` (git-ignored).
- Machine-level defaults (cpu, memory, disk_gb, network, state) belong in `config/catalog.yaml` under the machine's `defaults:` block.
- Local catalog overrides (different machine sizes, personal zvol paths, etc.) go in `config/catalog.local.yaml` (git-ignored).
- Scripts and terraform modules may declare variable defaults as a safety net (e.g. a terraform `default = "..."`) but the canonical, human-readable default always lives in `.env` or the catalog.

## Privacy and sensitive files

**Never read `.env.local`, `config/catalog.local.yaml`, or any other git-ignored file that may contain secrets, credentials, or personal configuration.** These files exist for the user to store sensitive data (API keys, passwords, personal server addresses) that must not be exposed to LLM context. If you need to know a value from these files, ask the user to provide it explicitly rather than reading the file.

## Git workflow

**Do not commit or push unless the user explicitly asks.** Stage changes with `git add` to avoid the terramate "repository has uncommitted files" error (terramate refuses to run when the working tree is dirty), but leave committing and pushing to the user.

When the user asks to commit:

1. Run `git status`, `git diff --staged`, and `git log --oneline -5` in parallel.
2. Draft a commit message following the project's conventional commit style.
3. Commit with `git commit` and push with `git push` only after the user approves.

## Sorting convention

Keep all lists alphabetically sorted unless there is an explicit ordering requirement (e.g. provisioning step numbers). This applies to:

- `Makefile` — `export` block, `.PHONY` targets, target definitions
- `.env` — section headers and variable declarations within each section
- `config/catalog.yaml` — entries within `machines`, `oses`, `inits`, `packages`, `bundles`, `locations`, `recipes`
- `scripts/provision` — the `state/env` heredoc
- Any other enumerated lists, arrays, or key-value blocks

When adding a new entry, insert it in alphabetical position rather than appending to the end.

## Project layout

```
config/
  catalog.yaml                # Single source of truth: machines / oses / inits / bundles / locations / recipes
  catalog.local.example.yaml  # Template for personal overrides
  catalog.local.yaml          # Personal overrides (git-ignored, merged over base)
modules/
  aws/ec2/                    # AWS EC2 instance + VPC + security group
  vultr/instance.tm.hcl       # os_family-aware Vultr module (Windows script vs Linux cloud-init)
  truenas/vm.tm.hcl           # truenas_zvol + cloud-init + truenas_vm
stacks/
  aws/        truenas/        vultr/       # 10-shared (networking) + 20-services per provider
scripts/
  profile-resolve             # Lower-level compatibility resolver for recipe/overlay compositions
  recipes-list                # List reusable VM recipes with details
  instance-ip / instance-ssh    # Instance IP + SSH wrappers (engine/provider aware)
  tf-env                      # Emits TF_VAR_* exports, gated by provider
  provision                   # Upload + run the OS-appropriate provisioning tree
  ssh-wait                    # Poll SSH until reachable
  logs                        # Stream remote provisioning logs
  start / stop / status       # Power on/off and status for all providers
  instance-password            # Display the instance's default password (Windows)
  tf-init / tf-plan / tf-apply / tf-destroy  # Terraform dispatchers used by provider plugins
  vagrant-up / vagrant-destroy  # Vagrant dispatchers (for local-* providers)
  truenas-cloudinit-upload    # Generates NoCloud seed ISO and uploads to TrueNAS REST API
  truenas-cloudinit-delete    # Removes cloud-init ISO from TrueNAS on destroy
  test / test-recipes / test-instances / test-lint  # Test suite
linux/provision/               # Bash state-machine runner (systemd unit)
  scripts/bootstrap.sh / runner.sh / lib/common.sh / steps/NN_*.sh
windows/provision/             # PowerShell state-machine runner (Scheduled Task)
  scripts/bootstrap.ps1 / runner.ps1 / lib/*.ps1 / steps/NN_*.ps1
tests/golden/                  # Frozen recipe/instance env snapshots
.github/workflows/test.yml     # CI: runs make test
.env                           # Canonical defaults (committed, no secrets)
.env.local                     # Personal secrets and overrides (git-ignored)
```

## Adding a new env variable

1. Add it (commented, with its default) to `.env` with a short inline comment.
2. Export it in the `Makefile` export block.
3. Thread it through `scripts/tf-env` as a `TF_VAR_*` if terraform needs it (remember to gate it inside the right `PROVIDER` case), or use it directly via the exported environment.
4. Do **not** use `${VAR:-fallback}` in scripts — the fallback belongs in `.env`.

## Adding a new recipe / machine / OS / bundle

1. Edit `config/catalog.yaml` — add entries under the relevant top-level key (`machines`, `oses`, `inits`, `bundles`, `locations`, or `recipes`).
2. Run `scripts/profile-resolve --profile <name> --validate` to confirm catalog consistency. The script name is kept for lower-level compatibility; user-facing commands should use `INSTANCE=`.
3. If the new recipe changes emitted env, run `make test.update-golden` to refresh `tests/golden/<name>.env`.
4. Run `make test` — all suites must pass before committing.

## Provider conventions

- Provider blocks and `required_providers` live in `providers.tm.hcl` files, not in stack or resource config files.
- Each provider's variables (host, key paths, ports) are declared alongside the provider block in the same generated file.
- Instance/recipe-driven values (region, instance type, plan, OS id, AZ) are threaded through as `TF_VAR_*` from `scripts/tf-env`; do **not** hardcode them in stack globals.
- TrueNAS is a special case: the parent `stacks/truenas/providers.tm.hcl` generates only `required_version`; the child `stacks/truenas/20-services/providers.tm.hcl` generates the full provider + variables (which the module at `modules/truenas/vm.tm.hcl` then relies on — see the note at `null_resource.cloudinit_iso` about `var.truenas_host`).

## Windows SSH shell

The Windows SSH server default shell is **PowerShell** (not `cmd.exe`). All scripts that send remote commands via `instance-ssh --` to a Windows host use PowerShell syntax directly — there is no `cmd.exe` fallback. When writing new SSH-invoked commands for Windows instances, use PowerShell cmdlets and syntax.

## No fallbacks

This project provisions environments from scratch — we control the OS, installed packages, shell, and runtime versions. **Never add fallback logic** (e.g. "try PowerShell, fall back to cmd.exe" or "check both Program Files and AppData just in case"). Always use the single correct path for the environment we build. If the environment changes, change the script — don't layer on fallbacks that mask the real requirement.

## Catalog kinds: vm vs metal

Machine entries declare a `kind:` field. Current supported kinds:

- `kind: vm` — disposable VM lifecycle (aws, vultr, truenas, local-virtualbox, local-vmware). `up` creates, `down` deletes.
- `kind: metal` — persistent hardware (planned: raspberry-pi). `down` tears down managed workloads, **not** the machine. Don't force metal targets through VM lifecycle assumptions.

See [docs/raspberry-pi-provider.md](docs/raspberry-pi-provider.md) for the metal design guardrails.

## Post-boot provisioning

Per-instance post-boot provisioning is OS-family driven:

- `linux/provision/` — bash state-machine runner for Ubuntu/Linux hosts.
- `windows/provision/` — PowerShell state-machine runner for Windows hosts.

Both use the same shape: `bootstrap` registers a runner (systemd unit or Scheduled Task), the runner walks a sorted `steps/` directory, and a `state.json` file tracks `currentStep` so provisioning is resumable across reboots. Steps are package-aware: a Linux step exits 0 early if its package id is not selected for the instance.

Entry points:
- `make provision INSTANCE=…` — uploads the right `<os>/provision/` tree and runs bootstrap. Dispatches by `os_family` resolved from the instance.
- `make ssh INSTANCE=…` — SSH using the correct user (`ubuntu` for Linux, `Administrator` for Windows) and resolved IP.
- `make ip INSTANCE=…` — print the instance IP (terraform output or `vagrant ssh-config`).
- `make logs INSTANCE=…` — stream remote provisioning logs.

Adding a new Linux step:
1. Drop `linux/provision/scripts/steps/NN_<name>.sh` (NN controls order).
2. Source `$PROVISION_ROOT/scripts/lib/common.sh` for helpers (`log`, `apt_install`, `has_pkg`, `skip_unless_pkg`, `is_desktop`, `request_reboot`). Add `# shellcheck source=../lib/common.sh` above the source line.
3. Call `skip_unless_pkg <package-id>` at the top if the step is bundle-gated.
4. Keep steps idempotent — they will re-run if provisioning is restarted.

## Testing

`make test` runs the suites from `scripts/test`:

- **recipes** (`test-recipes`) — resolves every recipe in `config/catalog.yaml`, diffs the emitted env against `tests/golden/<name>.env`. `UPDATE_GOLDEN=1` (or `make test.update-golden`) regenerates the snapshots. Determinism: TRUENAS_* and SSH_PUBLIC_KEY_FILE are unset inside the runner so golden output doesn't depend on the developer's environment.
- **instances** (`test-instances`) — validates local instance registry fixtures, generated overlays, provider dispatch routing, and state contracts.
- **terraform** (`test-terraform`) — `terramate generate` + `terraform init -backend=false` + `terraform validate` across `aws-services`, `vultr-services`, `truenas-services`. Uses a fake `MY_IP` and a tempfile SSH key. No cloud credentials required.
- **shellcheck** (`test-shellcheck`) — runs `shellcheck -x --source-path=SCRIPTDIR` over every shell script with a bash/sh shebang in `scripts/` and `linux/provision/`.
- **python** (`test-python`) — runs ruff and strict mypy for Python TUI code.
- **lint** (`test-lint`) — checks Ruby syntax, YAML syntax, Terraform formatting, and Terramate formatting.

CI runs the same target via [.github/workflows/test.yml](.github/workflows/test.yml) on push to `main` and every pull request.

When adding a shell script: ensure `#!/usr/bin/env bash|sh`, run `make test.shellcheck` locally, and fix warnings (or add a narrow `# shellcheck disable=SCnnnn` with a one-line justification).

## TrueNAS VM lifecycle

`up` for a TrueNAS profile:
1. Creates a `truenas_zvol` (empty block device at `/dev/zvol/<pool>/vms/<vm_name>`).
2. Generates a NoCloud cloud-init seed ISO locally (`hdiutil makehybrid`) and uploads it to TrueNAS via REST API (`TRUENAS_API_KEY`).
3. Creates the `truenas_vm` with the zvol as `disk` and the ISO as `cdrom`, started (`state = RUNNING`).

**One-time manual step**: write the Ubuntu cloud image to the zvol before the VM can boot (see README.md → TrueNAS setup).

`down` removes the VM, zvol, and cloud-init ISO.
