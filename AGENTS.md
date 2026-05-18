# Agent / AI Contributor Guidelines

## Configuration and defaults

**All configurable defaults live in `.env`, `config/defaults.yaml`, or the catalog.** Never use shell `${VAR:-default}` to encode a meaningful default inside a script. If a variable needs a default, declare it (commented or uncommented) in one of those files so it is discoverable in one place.

- User-specific overrides go in `.env.local` (git-ignored).
- Non-secret structured preferences go in `.egame/config.yaml` (git-ignored), using `config/defaults.yaml` as the documented shape.
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
- `config/catalog.yaml` — entries within `machines`, `oses`, `inits`, `packages`, `bundles`, `locations`
- `scripts/provision` — the `state/env` heredoc
- Any other enumerated lists, arrays, or key-value blocks

When adding a new entry, insert it in alphabetical position rather than appending to the end.

## Project layout

```
config/
  catalog.yaml                # Single source of truth: machines / oses / inits / bundles / locations
  catalog.local.example.yaml  # Template for personal overrides
  catalog.local.yaml          # Personal overrides (git-ignored, merged over base)
stacks/
  config.tm.hcl               # Legacy shared Terramate globals only
plugins/providers/
  aws/                         # AWS plugin, Terramate stacks, EC2 modules
  gcp/                         # GCP plugin, Terramate stacks, Compute modules
  truenas/                     # TrueNAS plugin, Terramate stacks, VM module
  vultr/                       # Vultr plugin, Terramate stacks, instance module
scripts/
  catalog-options             # List provider/platform/content choices
  profile-resolve             # Lower-level compatibility resolver for generated overlays
  instance-ip / instance-ssh    # Instance IP + SSH wrappers (engine/provider aware)
  tf-env                      # Emits TF_VAR_* exports, gated by provider
  provision                   # Upload + run the OS-appropriate provisioning tree
  ssh-wait                    # Poll SSH until reachable
  logs                        # Stream remote provisioning logs
  start / stop / status       # Power on/off and status for all providers
  instance-password            # Display the instance's default password (Windows)
  tf-init / tf-plan / tf-apply / tf-destroy  # Terraform dispatchers used by provider plugins
  vagrant-up / vagrant-destroy  # Vagrant dispatchers for local-qemu
  truenas-cloudinit-upload    # Generates NoCloud seed ISO and uploads to TrueNAS REST API
  truenas-cloudinit-delete    # Removes cloud-init ISO from TrueNAS on destroy
  test / test-catalog / test-core-boundary / test-instances / test-lint  # Test suite
oses/<catalog-os-id>/provision/       # Bash state-machine runner (systemd unit)
  scripts/bootstrap.sh / runner.sh / lib/common.sh / steps/NN_*.sh
oses/windows-server-2025/provision/             # PowerShell state-machine runner (Scheduled Task)
  scripts/bootstrap.ps1 / runner.ps1 / lib/*.ps1 / steps/NN_*.ps1
tests/golden/                  # Frozen instance env snapshots
.github/workflows/test.yml     # CI: runs make test
.env                           # Canonical defaults (committed, no secrets)
.env.local                     # Personal secrets and overrides (git-ignored)
```

## Adding a new env variable

1. Add it (commented, with its default) to `.env` with a short inline comment.
2. Export it in the `Makefile` export block.
3. Thread it through `scripts/tf-env` as a `TF_VAR_*` if terraform needs it (remember to gate it inside the right `PROVIDER` case), or use it directly via the exported environment.
4. Do **not** use `${VAR:-fallback}` in scripts — the fallback belongs in `.env`.

## Adding a new machine / OS / init / bundle

1. Edit `config/catalog.yaml` — add entries under the relevant top-level key (`machines`, `oses`, `inits`, `bundles`, `packages`, or `locations`).
2. Run `make catalog.list` to confirm the provider/platform/content choices are exposed as expected.
3. If instance resolution changes emitted env, run `make test.update-golden` to refresh `tests/golden/instances/<name>.env`.
4. Run `make test` — all suites must pass before committing.

## Init model

Init entries are bootstrap/access methods, not user-facing workload choices. They exist so the manager can reach a machine and start normal provisioning, usually through SSH. Prefer exactly one valid init for a given provider/machine/OS combination and let `instance-create` infer it.

- Use `providers: [...]` on init entries to bind them to provider implementations such as `raspberry-pi` or `vultr`.
- Do not add descriptive-only fields such as `features`; package and bundle manifests model capabilities.
- Only expose or require `INIT=` when there is a real ambiguous bootstrap choice for the same provider/machine/OS combination.
- Keep graphical/user tooling decisions in packages and bundles, not in init metadata.
- SSH is baseline management access from init/provider plumbing. Do not model SSH as a removable package or bundle entry.

## Provider conventions

- Provider blocks and `required_providers` live in `providers.tm.hcl` files, not in stack or resource config files.
- Each provider's variables (host, key paths, ports) are declared alongside the provider block in the same generated file.
- Instance-driven values (region, instance type, plan, OS id, AZ) are threaded through as `TF_VAR_*` from `scripts/tf-env`; do **not** hardcode them in stack globals.
- Terraform/Terramate provider implementations live with their provider plugins under `plugins/providers/<id>/stacks/` and `plugins/providers/<id>/modules/`. The remaining top-level `stacks/config.tm.hcl` is legacy shared global context only; do not add new provider implementation files there.
- TrueNAS is a special case inside that layout: the parent `providers.tm.hcl` generates only `required_version`; the child `20-services/providers.tm.hcl` generates the full provider + variables (which the module then relies on — see the note at `null_resource.cloudinit_iso` about `var.truenas_host`).

## Windows SSH shell

The Windows SSH server default shell is **PowerShell** (not `cmd.exe`). All scripts that send remote commands via `instance-ssh --` to a Windows host use PowerShell syntax directly — there is no `cmd.exe` fallback. When writing new SSH-invoked commands for Windows instances, use PowerShell cmdlets and syntax.

## No fallbacks

This project provisions environments from scratch — we control the OS, installed packages, shell, and runtime versions. **Never add fallback logic** (e.g. "try PowerShell, fall back to cmd.exe" or "check both Program Files and AppData just in case"). Always use the single correct path for the environment we build. If the environment changes, change the script — don't layer on fallbacks that mask the real requirement.

## Catalog kinds: vm vs metal

Machine entries declare a `kind:` field. Current supported kinds:

- `kind: vm` — disposable VM lifecycle (`aws`, `gcp`, `vultr`, `truenas`, `local-qemu`). `up` creates, `down` deletes.
- `kind: metal` — persistent hardware (`raspberry-pi`). `down` tears down managed workloads, **not** the machine. Don't force metal targets through VM lifecycle assumptions.

See [docs/raspberry-pi-provider.md](docs/raspberry-pi-provider.md) for the metal design guardrails.

## Language policy

- **Core orchestration:** Ruby. All new orchestration scripts under `scripts/` must be Ruby (`#!/usr/bin/env ruby`).
- **Guest-side provisioning:** bash under `oses/<catalog-os-id>/provision/` for Linux, PowerShell under `oses/windows-server-2025/provision/` for Windows. These are the only places new bash is acceptable.
- **TUI:** Python. The TUI (`scripts/egame-tui`) stays Python because Textual is Python.
- **No new bash in `scripts/`.** The boundary lint (`make test.core-boundary`) enforces this; existing bash scripts are enumerated in `scripts/test-core-boundary.allowlist` and will be ported to Ruby over time.

## Post-boot provisioning

Per-instance post-boot provisioning is OS-family driven:

- `oses/ubuntu-26.04/provision/` — shared bash state-machine runner for catalog Ubuntu OSes; `oses/ubuntu-26.04-amd64/provision` and `oses/ubuntu-26.04-arm64/provision` point here.
- `oses/windows-server-2025/provision/` — PowerShell state-machine runner for Windows hosts.

Both use the same shape: `bootstrap` registers a runner (systemd unit or Scheduled Task), the runner walks a sorted `steps/` directory, and a `state.json` file tracks `currentStep` so provisioning is resumable across reboots. Steps are package-aware: a Linux step exits 0 early if its package id is not selected for the instance.

Entry points:
- `make provision INSTANCE=…` — uploads the right `<os>/provision/` tree and runs bootstrap. Dispatches by `os_family` resolved from the instance.
- `make ssh INSTANCE=…` — SSH using the correct user (`ubuntu` for Linux, `Administrator` for Windows) and resolved IP.
- `make ip INSTANCE=…` — print the instance IP (terraform output or `vagrant ssh-config`).
- `make logs INSTANCE=…` — stream remote provisioning logs.

Adding a new Linux step:
1. Drop `oses/<catalog-os-id>/provision/scripts/steps/NN_<name>.sh` (NN controls order).
2. Source `$PROVISION_ROOT/scripts/lib/common.sh` for helpers (`log`, `apt_install`, `has_pkg`, `skip_unless_pkg`, `request_reboot`). Add `# shellcheck source=../lib/common.sh` above the source line.
3. Call `skip_unless_pkg <package-id>` at the top if the step is bundle-gated.
4. Keep steps idempotent — they will re-run if provisioning is restarted.

## Testing

`make test` runs the suites from `scripts/test`:

- **catalog** (`test-catalog`) — validates provider/platform/content choice emission and provider-specific OS image metadata gating.
- **core-boundary** (`test-core-boundary`) — fails if central `scripts/` reference provider or catalog OS IDs outside a committed allowlist of known violations.
- **instances** (`test-instances`) — validates local instance registry fixtures, generated overlays, provider dispatch routing, and state contracts.
- **lifecycle** (`test-lifecycle`) — exercises fake-provider up/status/ip/stop/down/start state transitions through `provider-dispatch`, asserting provider state and observed-state cache transitions. No live VM, no cloud credentials.
- **plugins** (`test-plugins`) — validates plugin manifests and dry-run dispatch contracts.
- **provision-runner** (`test-provision-runner`) — directly executes Ubuntu (bash) and optional Windows (PowerShell) provision runners in tempdirs, asserting step status, resume behaviour, manifest validation, and structured status output. Skips host-incompatible checks with `[SKIP]`.
- **terraform** (`test-terraform`) — `terramate generate` + `terraform init -backend=false` + `terraform validate` across `aws-services`, `gcp-services`, `vultr-services`, and `truenas-services`. Uses a fake `MY_IP` and a tempfile SSH key. No cloud credentials required.
- **shellcheck** (`test-shellcheck`) — runs `shellcheck -x --source-path=SCRIPTDIR` over every shell script with a bash/sh shebang in `scripts/` and `oses/<catalog-os-id>/provision/`.
- **python** (`test-python`) — runs ruff and strict mypy for Python TUI code.
- **schemas** (`test-schemas`) — validates JSON Schemas (draft 2020-12) for resolved instance, observed state, plugin manifests, and command I/O. Checks all shipped manifests, fixture instances, and negative-test fixtures. Uses Ruby `json_schemer`.
- **lint** (`test-lint`) — checks Ruby syntax, YAML syntax, Terraform formatting, and Terramate formatting.

CI runs the same target via [.github/workflows/test.yml](.github/workflows/test.yml) on push to `main` and every pull request.

When adding a shell script: ensure `#!/usr/bin/env bash|sh`, run `make test.shellcheck` locally, and fix warnings (or add a narrow `# shellcheck disable=SCnnnn` with a one-line justification).

## TrueNAS VM lifecycle

`up` for a TrueNAS instance:
1. Creates a `truenas_zvol` (empty block device at `/dev/zvol/<pool>/vms/<vm_name>`).
2. Generates a NoCloud cloud-init seed ISO locally (`hdiutil makehybrid`) and uploads it to TrueNAS via REST API (`TRUENAS_API_KEY`).
3. Creates the `truenas_vm` with the zvol as `disk` and the ISO as `cdrom`, started (`state = RUNNING`).

**One-time manual step**: write the Ubuntu cloud image to the zvol before the VM can boot (see README.md → TrueNAS setup).

`down` removes the VM, zvol, and cloud-init ISO.
