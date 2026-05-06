# v3: Instance-Driven VM Platform

## Why this evolution

This repo started as a strong **ephemeral cloud gaming** setup.
The next step is to make it a general **machine composition platform** where cloud/local/metal targets all use the same layered model.

Your key idea is correct: provider and installed software should be decoupled.

---

## Core model: 4 layers

Every environment should be composed from 4 explicit layers:

1. **Machine layer**
   - Provider/runtime specifics: AWS, Vultr, VirtualBox, VMware, TrueNAS VM, Raspberry Pi/metal, etc.
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

Access is no longer tied to one preset path. It is expressed as bundles/components:

- `ssh`
- `rdp` (Windows or Linux GUI workloads if needed)
- `sunshine`
- `rustdesk`

### Sunshine + RustDesk notes

- **Sunshine**: best for low-latency streaming workflows (gaming / high-FPS desktop interaction).
- **RustDesk**: best for admin/support fallback and remote troubleshooting.
- Recommended combo for GUI machines: `sunshine + rustdesk + ssh`.
- For headless dev sandboxes: usually `ssh` only.

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
- concrete instances in `.egame/instances.yaml` (composition entries)

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

  - name: local-virtualbox-medium
    provider: local-virtualbox
    kind: vm
    defaults:
      cpus: 4
      memory_mb: 8192
      disk_gb: 100

  - name: local-vmware-medium
    provider: local-vmware
    kind: vm
    defaults:
      cpus: 4
      memory_mb: 8192
      disk_gb: 100

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
    features: [ssh, hardening, nonroot-user]

  - id: ssh-windows-powershell7
    os_family: windows
    features: [ssh, hardening]

  - id: ssm-aws-linux
    os_family: ubuntu
    provider: aws
    features: [ssm, ssh-optional]

packages:
  - id: goose
  - id: codex-cli
  - id: docker
  - id: dev-toolchain
  - id: sunshine
  - id: rustdesk
  - id: steam

bundles:
  - id: access-headless
    includes: [ssh]

  - id: access-gui-safe
    includes: [rustdesk]

  - id: access-gui-streaming
    includes: [rustdesk, sunshine]

  - id: dev-sandbox-core
    includes: [docker, dev-toolchain, goose, codex-cli]

  - id: gaming-core
    includes: [sunshine, steam, rustdesk]

locations:
  - name: tokyo
    aws:
      region: ap-northeast-1
      availability_zone: ap-northeast-1b
    vultr:
      region: nrt
    local-virtualbox:
      host: local
    local-vmware:
      host: local

instances:
  - name: aws-ubuntu-dev-headless
    machine: aws-cheap-x86
    os: ubuntu-26.04-amd64
    init: ssh-ubuntu-cloud-init
    bundles: [access-headless, dev-sandbox-core]
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
    bundles: [access-gui-safe, dev-sandbox-core]
    location: tokyo

  - name: vultr-windows-gaming
    machine: vultr-vcg-a40-2c
    os: windows-server-2025
    init: ssh-windows-powershell7
    bundles: [access-gui-streaming, gaming-core]
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

Given your current Terramate/Terraform layout:

- Keep existing `stacks/aws/*` and `stacks/vultr/*` working.
- Add a generated layer that resolves one concrete instance into provider-specific working files and Terraform/Terramate inputs.
- Existing provider blocks (`aws`, `vultr`) and local backend setup remain valid.

### Suggested incremental implementation

## Phase 1: Manifest + resolver (no behavior break)

- Add `config/catalog.yaml` with machine/os/init/package/location catalogs.
- Add a small resolver script to produce provider inputs for selected instances.
- Keep current gaming stack as an instance composition.

## Phase 2: New instance target

- Implement `aws-ubuntu-dev-headless` end-to-end.
- Add `make plan INSTANCE=aws-ubuntu-dev-headless` etc.

## Phase 3: GUI and remote access bundles

- Add `access-gui-safe` (RustDesk) and `access-gui-streaming` (Sunshine+RustDesk).
- Add Linux GUI package bundles.

## Phase 4: Local providers (Vagrant-first)

- Implement `local-virtualbox` and `local-vmware` using **Vagrant** as the primary local orchestration layer.
- Use Vagrant provider plugins (VirtualBox / VMware) to avoid re-implementing VM lifecycle plumbing.
- Keep `VBoxManage`/`vmrun` wrappers only as fallback for edge cases or environments where Vagrant is unavailable.

## Phase 5: Additional runtimes

- TrueNAS-hosted VM mapping.
  - Catalog scaffold is in place (`provider: truenas` + sample instance).
  - Terramate stack/module implementation is in place (`stacks/truenas/*`, `modules/truenas/*`) with `deevus/truenas` provider and `truenas_vm` resource wiring.
  - Current instance defaults are conservative (STOPPED by default, explicit SSH host key fingerprint required).
- USB/metal (Raspberry Pi) machine kind with cloud-init/ansible init adaptation.
  - Prefer a dedicated machine/provider model such as `provider: raspberry-pi`, `kind: metal`.
  - Treat it as a persistent ARM sandbox target, not as a local hypervisor abstraction.
  - Reuse the same workload/bundle layer as Ubuntu cloud/local VM targets where possible.

---

## Local implementation strategy (reduce wheel reinvention)

For local providers, prefer existing ecosystem tooling first.

### Primary: Vagrant orchestration

Use Vagrant as the local runtime abstraction for:

- `local-virtualbox` (VirtualBox provider)
- `local-vmware` (VMware provider)

Benefits:

- standard `up/halt/destroy/provision` lifecycle
- mature box/template workflows
- easier SSH metadata discovery and provisioning handoff
- less custom lifecycle scripting in this repo

### Fallback: direct hypervisor CLI wrappers

Use `VBoxManage` / `vmrun` wrappers only when:

- Vagrant provider support is insufficient for a required feature
- host constraints prevent Vagrant usage
- specialized snapshot/network behavior is needed

### Suggested mapping

- `machine.provider = local-virtualbox` → Vagrant + VirtualBox provider
- `machine.provider = local-vmware` → Vagrant + VMware provider
- resolver emits provider-specific Vagrantfile fragments from the same manifest model

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
- Backend should call existing instance commands/resolver (`scripts/instance-resolve`, `make instance.*`) instead of duplicating orchestration logic

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

- add lightweight API wrapper over `instance-resolve` + `make instance.*`
- add web GUI for instance lifecycle and observability
- keep CLI parity (GUI is additive, not replacement)

---

## Makefile direction

Keep commands instance-first:

```bash
make catalog.list
make instance.create INSTANCE=aws-dev-a MACHINE=aws-cheap-x86 OS=ubuntu-26.04-amd64 INIT=ssh-ubuntu-cloud-init LOCATION=tokyo BUNDLES=access-headless,dev-sandbox-core
make instance.validate INSTANCE=aws-dev-a
make plan INSTANCE=aws-dev-a
make up INSTANCE=aws-dev-a
make provision INSTANCE=aws-dev-a
make down INSTANCE=aws-dev-a
```

---

## Recommendation summary

For your immediate safe sandbox need:

- Start with instance: `aws-ubuntu-dev-headless`
- OS: `ubuntu-26.04-amd64`
- Access bundle: `ssh` only
- Workloads: `goose + codex-cli + docker + dev-toolchain`
- Lifecycle: 7-day TTL with reminders and stop→grace→destroy flow

For GUI-required workflows, add:

- instance: `aws-ubuntu-dev-gui`
- OS: `ubuntu-26.04-amd64`
- Access bundle: `sunshine + rustdesk + ssh`

This gives a clean layered system while preserving your existing cloud gaming workflows.
