# v3: Instance-Driven VM Platform

## Why this evolution

This repo started as a strong **ephemeral cloud gaming** setup.
The next step is to make it a general **machine composition platform** where cloud/local/metal targets all use the same layered model.

Your key idea is correct: provider and installed software should be decoupled.

---

## Core model: 4 layers

Every environment should be composed from 4 explicit layers:

1. **Machine layer**
   - Provider/runtime specifics: AWS, GCP, Vultr, QEMU, TrueNAS VM, Raspberry Pi/metal, etc.
   - Example fields: instance type/plan, disk, CPU/RAM, network mode, provider tags.

2. **OS layer**
   - Concrete OS image/version (not generic “linux”).
   - Example: `ubuntu-26.04-amd64`, `ubuntu-26.04-arm64`, `windows-server-2025`.

3. **Init layer**
   - First-boot bootstrap to establish secure access and baseline hardening.
   - Example: `ssh-ubuntu-cloud-init`, `ssh-windows-powershell7`, `ssm-aws-linux`.

4. **Workload layer**
   - What you install for purpose: Goose, Codex, Sunshine, Steam, RustDesk, toolchains, etc.
   - This should be composable as package/bundle lists.

This layered approach replaces rigid provider/os/purpose presets and avoids combinatorial explosion.

---

## Access methods (requested)

SSH management access is provided by init and is always expected. User-facing
remote access beyond that is expressed as bundles/components:

- `rdp` (Windows or Linux GUI workloads if needed)
- `sunshine`
- `rustdesk`

### Sunshine + RustDesk notes

- **Sunshine**: best for low-latency streaming workflows (gaming / high-FPS desktop interaction).
- **RustDesk**: best for admin/support fallback and remote troubleshooting.
- Recommended combo for GUI machines: `sunshine + rustdesk` plus baseline SSH.
- For headless dev sandboxes: baseline SSH is enough unless dev packages are selected.

---

## OS naming and recommended defaults

Use explicit OS catalog IDs (version + arch). Avoid generic `linux` in instance definitions.

Recommended starter OSes:

1. `ubuntu-26.04-amd64` (default for Linux dev/sandbox and optional GUI workloads)
2. `ubuntu-26.04-arm64` (for ARM hosts, e.g. QEMU/RPi flows)
3. `windows-server-2025` (for Windows-native/gaming workflows)

Optional later:

- `debian-12-server-amd64` (stable/minimal alternative)
- `debian-13-amd64` (stable/minimal alternative once provider image metadata exists)

### Graphical Workloads

Graphical capabilities are selected through packages and bundles rather than an
OS-wide setting. For example, selecting `gnome-desktop`, `vnc`, `rustdesk`,
`sunshine`, or `steam` installs the relevant graphical stack.

This lets one workload catalog run on both, with compatibility checks.

---

## Data model (manifest-driven)

Instead of path-only presets like `aws/linux/dev-sandbox`, define reusable catalogs:

- `machines[]`
- `oses[]`
- `inits[]`
- `packages[]` and/or `bundles[]`
- `locations[]`
- concrete instances in `.eve/instances.yaml` (composition entries)

## Example manifest (aligned with your idea)

For repository consumers, keep base definitions in `config/catalog.yaml` and allow personal overrides in `config/catalog.local.yaml` (git-ignored) to avoid local customization causing a dirty git state.

```yaml
version: 1

machines:
  - name: aws-cheap-x86
    provider: aws
    kind: vm
    defaults:
      instance_type: t3.large
      disk_gb: 80
      root_volume_type: gp3

  - name: aws-gpu-g5
    provider: aws
    kind: vm
    defaults:
      instance_type: g5.2xlarge
      disk_gb: 200

  - name: vultr-vcg-a40-1c # 1 vCPU, 5 GB RAM, 90 GB NVMe, 3 TB/mo, $0.075/hr, 1/24 NVIDIA A40 (2 GB VRAM)
    provider: vultr
    kind: vm
    defaults:
      plan: vcg-a40-1c-5g-2vram

  - name: vultr-vcg-a40-2c # 2 vCPUs, 10 GB RAM, 180 GB NVMe, 4 TB/mo, $0.144/hr, 1/12 NVIDIA A40 (4 GB VRAM)
    provider: vultr
    kind: vm
    defaults:
      plan: vcg-a40-2c-10g-4vram

  - name: vultr-vcg-a40-4c # 4 vCPUs, 20 GB RAM, 360 GB NVMe, 5 TB/mo, $0.288/hr, 1/6 NVIDIA A40 (8 GB VRAM)
    provider: vultr
    kind: vm
    defaults:
      plan: vcg-a40-4c-20g-8vram

  - name: vultr-vcg-a40-6c # 6 vCPUs, 30 GB RAM, 550 GB NVMe, 6 TB/mo, $0.432/hr, 1/4 NVIDIA A40 (12 GB VRAM)
    provider: vultr
    kind: vm
    defaults:
      plan: vcg-a40-6c-30g-12vram

  - name: local-qemu-medium
    provider: local-qemu
    kind: vm
    defaults:
      cpus: 2
      memory_mb: 4096
      disk_gb: 20

oses:
  - id: ubuntu-26.04-server-amd64
    family: ubuntu
    version: "26.04"
    arch: amd64

  - id: windows-server-2025
    family: windows
    version: "2025"
    arch: amd64

inits:
  - id: ssh-ubuntu-cloud-init
    os_family: ubuntu
    providers: [aws, gcp, local-qemu, truenas]

  - id: ssh-windows-powershell7
    os_family: windows
    providers: [vultr]

packages:
  - id: goose
  - id: codex-cli
  - id: docker
  - id: dev-toolchain
  - id: sunshine
  - id: rustdesk
  - id: steam

bundles:
  - id: desktop-streaming
    includes: [rustdesk, sunshine, vnc, rdp, waypipe]

  - id: dev-ai
    includes: [docker, dev-toolchain, goose, codex-cli]

  - id: gaming-streaming
    includes: [sunshine, steam, rustdesk]

locations:
  - name: tokyo
    aws:
      region: ap-northeast-1
      availability_zone: ap-northeast-1b
    vultr:
      region: nrt
    local-qemu:
      host: local

instances:
  - name: aws-ubuntu-dev-headless
    machine: aws-cheap-x86
    os: ubuntu-26.04-amd64
    init: ssh-ubuntu-cloud-init
    bundles: [dev-ai]
    location: tokyo
    lifecycle:
      ttl_hours: 168
      reminder_hours: [24, 6, 1]
      on_expiry: stop_then_destroy
      grace_hours: 24

  - name: aws-ubuntu-dev-gui
    machine: aws-cheap-x86
    os: ubuntu-26.04-amd64
    init: ssh-ubuntu-cloud-init
    bundles: [desktop-streaming, dev-ai]
    location: tokyo

  - name: vultr-windows-gaming
    machine: vultr-vcg-a40-2c
    os: windows-server-2025
    init: ssh-windows-powershell7
    bundles: [desktop-streaming, gaming-streaming]
    location: tokyo
```

---

## Compatibility rules (important)

Introduce validation before provisioning:

1. `machine.provider` must support selected `os` image.
2. `init.os_family` must match selected OS family.
3. bundle/package compatibility checks:
   - `steam` requires an OS/package combination that can provide a graphical session.
   - `sunshine` requires an OS/package combination that can provide a graphical session.
   - `goose/codex-cli` can run without graphical packages.
4. location must define provider-specific mapping for chosen machine provider.

Fail fast at plan time with actionable errors.

---

## How this maps to current repo

Given the current Terramate/Terraform layout:

- Provider Terraform/Terramate implementation lives with each provider plugin
  under `plugins/providers/<id>/stacks/` and `plugins/providers/<id>/modules/`.
- Add a generated layer that resolves one concrete instance into provider-specific working files and Terraform/Terramate inputs.
- Existing provider blocks (`aws`, `vultr`) and local backend setup remain valid.

### Suggested incremental implementation

## Phase 1: Manifest + resolver (no behavior break)

- Add `config/catalog.yaml` with machine/os/init/package/location catalogs.
- Add a small resolver script to produce provider inputs for selected instances.
- Keep current gaming stack as an instance composition.

## Phase 2: New instance target

- Implement `aws-ubuntu-dev-headless` end-to-end.
- Add `eve instance up --instance aws-ubuntu-dev-headless` etc.

## Phase 3: GUI and remote access bundles

- Add `desktop-streaming` for Sunshine, RustDesk, VNC, RDP, and Waypipe.
- Add Linux GUI package bundles.

## Phase 4: Local provider

- Implement `local-qemu` using **Vagrant + qemu** as the local orchestration layer.
- Prefer QEMU as the only supported local provider, especially on Apple Silicon.

## Phase 5: Additional runtimes

- TrueNAS-hosted VM mapping.
  - Catalog scaffold is in place (`provider: truenas` + sample instance).
  - Terramate stack/module implementation is in place under `plugins/providers/truenas/` with `deevus/truenas` provider and `truenas_vm` resource wiring.
  - Current instance defaults are conservative (STOPPED by default, explicit SSH host key fingerprint required).
- USB/metal (Raspberry Pi) machine kind with cloud-init/ansible init adaptation.
  - Prefer a dedicated machine/provider model such as `provider: raspberry-pi`, `kind: metal`.
  - Treat it as a persistent ARM sandbox target, not as a local hypervisor abstraction.
  - Reuse the same workload/bundle layer as Ubuntu cloud/local VM targets where possible.

---

## Local implementation strategy (reduce wheel reinvention)

For the local provider, prefer existing ecosystem tooling first.

### Primary: Native QEMU orchestration

Use QEMU directly as the local runtime for:

- `local-qemu` (QEMU provider)

Benefits:

- standard `up/start/stop/down` lifecycle managed by the native provider command
- direct Ubuntu cloud image usage — no intermediate box format
- native QEMU monitor for graceful shutdown
- less dependency surface (no Vagrant, no plugins)

### Suggested mapping

- `machine.provider = local-qemu` → native QEMU orchestration
- resolver emits QEMU configuration from the same manifest model

This keeps the layered machine/OS/init/workload architecture intact while avoiding unnecessary reinvention.

---

## GUI / Web control plane roadmap (later phase)

A GUI is a great fit for this project, especially once instance resolution and engine dispatch are stable.

### Goal

Provide a simple control plane that uses the same backend instance engine (no separate logic):

- choose or create instance
- validate
- plan/apply/destroy
- inspect status/logs
- see TTL/reminders/expiry state

### Recommended approach

- **Web GUI first** (fastest iteration, easiest sharing)
- Optional desktop wrapper later (Tauri/Electron) if needed
- Backend should call existing instance commands/resolver (`scripts/instance-resolve`, `eve instance ...`) instead of duplicating orchestration logic

### Minimal backend API contract

- `GET /api/catalog` → return machine/os/init/package/location catalog
- `POST /api/instances/{name}/validate`
- `POST /api/instances/{name}/plan`
- `POST /api/instances/{name}/apply`
- `POST /api/instances/{name}/destroy`
- `GET /api/instances/{name}/status`
- `GET /api/instances/{name}/logs`
- `POST /api/instances/{name}/ttl/extend` (e.g., add hours)

Use job IDs for long-running actions (`plan/apply/destroy`) and expose:

- `GET /api/jobs/{id}`
- stream logs/events for progress UI

### Minimal UI screens

1. **Instance picker**
   - filter by provider, OS family, state, and selected bundles/packages
2. **Instance details**
   - resolved machine/os/init/packages/location + compatibility checks
3. **Lifecycle actions**
   - validate / plan / apply / destroy buttons
4. **Status + logs**
   - current state, last operation output, access info
5. **TTL panel**
   - expiry timestamp, reminders, extend TTL action

### Security baseline for GUI

- local-first auth (or SSO later)
- role separation:
  - read-only viewer
  - operator (apply/destroy)
- explicit confirmation for destructive actions
- audit trail for all lifecycle commands

### New phase suggestion

## Phase 6: Control plane UI

- add lightweight API wrapper over `instance-resolve` + `eve instance ...`
- add web GUI for instance lifecycle and observability
- keep CLI parity (GUI is additive, not replacement)

---

## CLI direction

Keep commands instance-first:

```bash
eve catalog list
eve instance create --instance aws-dev-a --machine aws-cheap-x86 --os ubuntu-26.04-amd64 --location tokyo --bundles dev-ai
eve instance validate --instance aws-dev-a
eve instance up --instance aws-dev-a
eve instance provision --instance aws-dev-a
eve instance down --instance aws-dev-a
```

---

## Recommendation summary

For your immediate safe sandbox need:

- Start with instance: `aws-ubuntu-dev-headless`
- OS: `ubuntu-26.04-amd64`
- Access: SSH is baseline management access from init.
- Workloads: `goose + codex-cli + docker + dev-toolchain`
- Lifecycle: 7-day TTL with reminders and stop→grace→destroy flow

For GUI-required workflows, add:

- instance: `aws-ubuntu-dev-gui`
- OS: `ubuntu-26.04-amd64`
- Access bundle: `sunshine + rustdesk`

This gives a clean layered system while preserving your existing cloud gaming workflows.
