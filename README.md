# v3: Instance-Driven VM Platform

> Work in progress: this repo is evolving from gaming-only infra into a layered machine-composition platform (machine + OS + init + workloads), supporting cloud and local targets.
>
> See: [docs/multi-purpose-vm-blueprint.md](docs/multi-purpose-vm-blueprint.md)
>
> Planned runtime notes: [docs/raspberry-pi-provider.md](docs/raspberry-pi-provider.md)

```bash
docker run -it mcr.microsoft.com/dotnet/sdk:9.0 pwsh

ssh vultr

ssh vultr 'Remove-Item -Recurse -Force C:\provision\*'
scp -r ~/src/personal/ephemeral-cloud-gaming/windows/provision/* vultr:/C:/provision/

ssh vultr "pwsh C:\provision\bootstrap.ps1"
```

## v3 instance workflow

v3 introduces concrete local instances selected from provider/platform catalog
choices. Instances live in the git-ignored local registry at
`.egame/instances.yaml`.

```bash
# List supported provider / platform / content choices
make catalog.list

# Create a concrete instance entry
make instance.create INSTANCE=dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=remote-waypipe DISK_GB=32

# List and inspect concrete instances
make instance.list
make instance.info INSTANCE=dev-a
make instance.env INSTANCE=dev-a
make instance.paths INSTANCE=dev-a
make instance.state INSTANCE=dev-a
make instance.status INSTANCE=dev-a EMIT=json
make instance.validate INSTANCE=dev-a

# Browse and operate instances from the optional Textual TUI
make tui

# Run existing profile-oriented targets through a generated instance overlay
make init INSTANCE=dev-a
make env INSTANCE=dev-a
make provision INSTANCE=dev-a
make ssh INSTANCE=dev-a

# Provisioning is stateful in v3; FORCE=1 clears remote provision state first
make instance.provision INSTANCE=dev-a FORCE=1

# Inspect plugin contracts and package lifecycle hooks
make plugins.list
make provider.status INSTANCE=dev-a
make package.list INSTANCE=dev-a
make package.select INSTANCE=dev-a PACKAGE=xpra
make package.status INSTANCE=dev-a PACKAGE=docker
make package.down INSTANCE=dev-a PACKAGE=docker YES=1
make package.unselect INSTANCE=dev-a PACKAGE=xpra
```

The v3 command surface is instance-first. The catalog defines machines, OSes,
init methods, locations, bundles, packages, and plugins; `.egame/instances.yaml`
defines concrete local instances composed from those catalog entries. Provider
and package plugins receive resolved instance JSON, and legacy profile-shaped
overlays are generated only as an internal compatibility detail for lower-level
provider scripts. Terraform-backed instances now get

The built-in Linux Docker package installs Docker in rootless mode. The daemon
runs as the VM user through `systemd --user`, and `DOCKER_HOST` points at the
user socket under `/run/user/<uid>/docker.sock`.

Experimental Wayland app forwarding is available through the `waypipe` package
and `remote-waypipe` bundle:

```bash
make package.select INSTANCE=dev-a PACKAGE=waypipe
make package.install INSTANCE=dev-a PACKAGE=waypipe
make remote.waypipe INSTANCE=dev-a APP=foot
```

On macOS, install a local Wayland-capable client side first. Current experiments
to try are [waypipe-darwin](https://github.com/J-x-Z/waypipe-darwin),
[Wawona](https://github.com/Wawona/Wawona), or
[wprs](https://github.com/wayland-transpositor/wprs). Treat this as a trial
path, not a stable replacement for Xpra yet.

Terraform-backed instances get instance-scoped backend roots and `TF_DATA_DIR` paths under
`.generated/instances/<name>/tf/`, so multiple concrete instances on the same
provider do not share local Terraform state.

Linux GUI packages are selected explicitly through bundles and packages.
For GNOME trials, select `gnome-desktop`; adding `macos-desktop-theme` applies a
best-effort dock-at-bottom, left-side window controls, dark color scheme, and
Papirus icon setup on the next GNOME login.

Providers and packages are now described by plugin manifests. Built-ins live in
`plugins/providers/<id>/egame-plugin.yaml` and
`plugins/packages/<id>/egame-plugin.yaml`; optional external plugins can be
pinned in `.egame/plugin-sources.yaml` and synchronized with
`make plugins.sync`. Package `down` and `reinstall` operations are explicit and
destructive removals require `YES=1`.

Plugin contracts and example external plugin layouts are documented in
[docs/plugins.md](docs/plugins.md).

Instance state contracts are documented in [docs/state.md](docs/state.md).

Manual and AI-assisted live test flow is documented in
[docs/integration-testing.md](docs/integration-testing.md). Start with
`make integration.plan INSTANCES=<linux>,<windows>`; live runs require
`YES=1 make integration.test INSTANCES=<linux>,<windows>`.
Optional host-side AI agent sandboxing is documented in
[docs/ai-sandboxes.md](docs/ai-sandboxes.md).

The optional `make tui` target opens a Textual instance manager for browsing
instances, combined state, package state, and safe provider/package actions.
Install Textual with `python3 -m pip install textual` when you want the TUI;
the rest of the v3 command surface has no Python package dependency.

Package plugins may provide host-side command hooks at
`commands/<os_family>/<install|status|down>` or
`commands/common/<install|status|down>`. The built-in compatibility wrapper
passes the resolved instance JSON on stdin and sets `EGAME_INSTANCE_NAME`,
`EGAME_PACKAGE_PLUGIN`, and `EGAME_PACKAGE_PLUGIN_ROOT`.

Manifest command `exec` paths may point at core repo scripts, such as
`scripts/package-plugin`, or at plugin-local executables. External plugins that
reuse a built-in id are rejected by default; set `EGAME_PLUGIN_ALLOW_OVERRIDE=1`
only when you intentionally want the later external plugin to replace the
built-in one.

`make instance.paths INSTANCE=<name>` shows the generated overlay path,
instance state file path, and Terraform artifact roots used by the bridge.

## Instance Workflow

Terraform provider versions are pinned exactly in the Terramate provider templates for reproducibility.

### Fresh checkout expectations

- Local instance choices (for example QEMU/Vagrant) should work without cloud API keys.
- Cloud providers (AWS/Vultr/TrueNAS) only require their own env vars when used.
- Keep personal settings in `.env.local`.

```bash
# List catalog choices and create a concrete instance
make catalog.list
make instance.create INSTANCE=dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=dev-ai-arm64

# Validate and inspect the instance
make validate INSTANCE=dev-a
make info INSTANCE=dev-a
```

Local customizations (without git-dirty state):

```bash
cp config/catalog.local.example.yaml config/catalog.local.yaml
# edit config/catalog.local.yaml for personal overrides
```

`config/catalog.local.yaml` is git-ignored and merged over the base catalog.

```bash
# Cloud instance (terraform engine)
make instance.create INSTANCE=aws-dev-a MACHINE=aws-cheap-x86 OS=ubuntu-26.04-amd64 LOCATION=tokyo BUNDLES=dev-ai
make init INSTANCE=aws-dev-a
make plan INSTANCE=aws-dev-a
make up INSTANCE=aws-dev-a
make provision INSTANCE=aws-dev-a
make ssh INSTANCE=aws-dev-a
make down INSTANCE=aws-dev-a

# Local instance (vagrant engine)
make instance.create INSTANCE=local-dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=dev-ai-arm64
make plan INSTANCE=local-dev-a
make up INSTANCE=local-dev-a
make down INSTANCE=local-dev-a

# TrueNAS instance (real provider wiring)
make instance.create INSTANCE=truenas-dev-a MACHINE=truenas-scale-medium OS=ubuntu-26.04-amd64 LOCATION=tokyo BUNDLES=dev-ai
make validate INSTANCE=truenas-dev-a
make info INSTANCE=truenas-dev-a

# Required env vars for provider auth:
# - TRUENAS_SSH_PRIVATE_KEY_FILE (path to private key)
# - TRUENAS_SSH_HOST_KEY_FINGERPRINT (e.g., SHA256:...)
# Optional: host/user/port from .env.local (TRUENAS_HOST/TRUENAS_SSH_USER/TRUENAS_SSH_PORT)

# Example (macOS/Linux):
# export TRUENAS_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/truenas_ed25519"
# export TRUENAS_SSH_HOST_KEY_FINGERPRINT="SHA256:..."

make init INSTANCE=truenas-dev-a
make plan INSTANCE=truenas-dev-a
make up INSTANCE=truenas-dev-a
make down INSTANCE=truenas-dev-a
```

## Post-boot provisioning (Linux + Windows)

After `up` creates an instance, run `provision` to install bundle packages:

```bash
make ssh.wait INSTANCE=aws-dev-a   # optional — wait for SSH
make provision INSTANCE=aws-dev-a  # installs selected package set
make logs INSTANCE=aws-dev-a       # tail remote logs
```

`make provision` dispatches by the instance OS family:

- Linux: uploads [linux/provision/](linux/provision/) to `$HOME/provision` on the VM, installs a `systemd` unit, and runs numbered package steps. Each step is skipped if its package id is not selected by the instance.
- Windows: uploads [windows/provision/](windows/provision/) to `C:\Users\Administrator\provision` and runs `bootstrap.ps1`, which registers a Scheduled Task that walks a similar sorted `steps/` directory. Requires `EPHEMERAL_WINDOWS_PASSWORD` (or a terraform output) and `EPHEMERAL_SUNSHINE_PASSWORD` — used to build `./tmp/env.json` and scp it into the provision state dir.

State is tracked in `$HOME/provision/state/state.json` on the VM — provisioning resumes from the last completed step after a reboot.

## Remote GUI apps via Xpra (no full desktop)

Xpra forwards individual remote applications over SSH and renders them as native-looking windows on the local host — useful when you want one remote app (e.g. a browser, IDE, or X11 tool) without pulling up a full remote desktop. Xpra is package-gated, so it is only installed on instances that opt in. The current upstream Xpra Linux packages require Python `< 3.13`; add it explicitly only when using a compatible OS/package source.

> Linux instances use virtual displays (`xpra start :N`). Windows instances use shadow mode via Scheduled Task + SSH tunnel.

### Local install (macOS)

1. **XQuartz** (X11 server) — `brew install --cask xquartz` (log out/in after first install).
2. **Xpra client** — install the **official signed `.pkg` from [xpra.org/install](https://xpra.org/install/)** (also linked from the project's [GitHub wiki](https://github.com/Xpra-org/xpra/wiki/Download)).

   > Do **not** use `brew install --cask xpra`. The Homebrew cask is deprecated (fails macOS Gatekeeper, scheduled for removal on 2026-09-01). The upstream `.pkg` is code-signed and notarized by the Xpra project.

### Local install (Linux)

```bash
sudo apt-get install xpra          # Debian/Ubuntu
# or follow https://github.com/Xpra-org/xpra/wiki/Download for other distros
```

### Enable on an instance

Select the package on a compatible instance:

```bash
make package.select INSTANCE=dev-a PACKAGE=xpra
make package.install INSTANCE=dev-a PACKAGE=xpra
```

### Launch an app

```bash
make remote.xpra INSTANCE=dev-a APP=xeyes          # smoke test
make remote.xpra INSTANCE=dev-a APP=firefox        # browser
make remote.xpra INSTANCE=dev-a APP="xterm -e htop"
```

The target starts an Xpra server on the VM, launches the requested app, and attaches a local client window. Use `make remote.xpra.stop INSTANCE=...` to stop the remote session.

## Provider setup guides

### Prerequisites (all providers)

- [Terramate](https://terramate.io/docs/cli/install) — code generation and stack management
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.4
- [Ruby](https://www.ruby-lang.org/en/documentation/installation/) — catalog YAML parsing in `profile-resolve` (`brew install ruby` on macOS)
- [jq](https://jqlang.github.io/jq/download/) — JSON processing for profile resolution (`brew install jq` on macOS)
- `make`

### AWS

1. **AWS CLI** — [install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
2. **Authenticate** — run `aws login` (or `aws sso login`) to refresh credentials
3. **Required env vars** (in `.env` or `.env.local`):
   - `AWS_PROFILE` — e.g. `hekk-dev`
   - `AWS_REGION` — e.g. `ap-northeast-1`

### Vultr

1. **API key** — [generate one](https://my.vultr.com/settings/#settingsapi)
2. **Required env vars** (in `.env` or `.env.local`):
   - `VULTR_API_KEY`

### TrueNAS

1. **SSH key** — generate a keypair for Terraform to use
2. **TrueNAS user** — create a Terraform user with SSH access and `terraform` group
3. **API key** — generate one in TrueNAS → API Keys (used for cloud-init ISO upload)
 4. **Required env vars** (in `.env.local`) — runtime errors out clearly if any are unset:
    - `TRUENAS_HOST` — e.g. `192.168.0.52` or `truenas.home.arpa`
    - `TRUENAS_SSH_USER` — e.g. `terraform` (required; no built-in default)
    - `TRUENAS_SSH_PRIVATE_KEY_FILE` — path to private key
    - `TRUENAS_SSH_HOST_KEY_FINGERPRINT` — e.g. `SHA256:...`
    - `TRUENAS_API_KEY` — REST API key for cloud-init ISO upload
    - `TRUENAS_VM_BASE_DIR` — base directory for VM files (e.g. `/mnt/pool1/egame`)
    - `TRUENAS_VM_POOL` — ZFS pool for zvols (e.g. `pool1`)
    - `TRUENAS_VM_ZVOL_PREFIX` — dataset path prefix for zvols (e.g. `egame`)
 5. **Optional env vars** (defaults in `.env`, override in `.env.local`):
    - `TRUENAS_SSH_PORT` (default: `22`)
 6. **One-time ZFS setup** — create the parent dataset:
    ```bash
    # On TrueNAS web UI: Storage > pool1 > Add Dataset (preset: Generic)
    #   Name: egame    →  creates pool1/egame
    ```
    The dataset (`pool1/egame`) must exist before `make up`. Subdirectories (`iso/`, `images/`) are created automatically.
 7. **One-time sudoers setup** — the Terraform user needs `sudo dd` access to write cloud images to zvols. Add to sudoers (`visudo` on TrueNAS):
    ```
    terraform ALL=(ALL) NOPASSWD: /usr/bin/dd if=/mnt/pool1/egame/images/* of=/dev/zvol/pool1/egame/*
    ```
    Adjust path to `/bin/dd` if using TrueNAS CORE (FreeBSD).
 8. **Disk image setup** — `make up` downloads the cloud image directly to the NAS, writes it to a zvol, and resizes the partition. No manual `dd` needed.

### QEMU (local, Apple Silicon ✅)

QEMU is the preferred local Linux provider on Apple Silicon. It uses the public
`cloud-image/ubuntu-26.04` Vagrant box with the `qemu` provider artifact.

1. **QEMU** — `brew install qemu`
2. **Vagrant** — `brew install hashicorp/tap/vagrant`
3. **Vagrant QEMU plugin** — `vagrant plugin install vagrant-qemu`
4. No cloud credentials needed

### VirtualBox (local, Intel macOS/Linux)

> **Note**: VirtualBox is kept as a legacy/local option. It can use
> `cloud-image/ubuntu-26.04`, but is not the recommended path on Apple Silicon.

1. **VirtualBox** — [install](https://www.virtualbox.org/wiki/Downloads) (version 7.1+)
2. **Vagrant** — `brew install hashicorp/tap/vagrant`
3. No cloud credentials needed

### VMware Fusion (local, legacy)

> **Note**: `cloud-image/ubuntu-26.04` does not publish a VMware Vagrant
> artifact, so VMware is not recommended for Ubuntu 26.04 unless you provide a
> compatible custom box.

1. **VMware Fusion** — [install](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion) (free for personal use)
2. **Vagrant** — `brew install hashicorp/tap/vagrant`
3. **Vagrant VMware plugin** — `vagrant plugin install vagrant-vmware-desktop`
4. **Vagrant VMware Utility** — `brew install --cask vagrant-vmware-utility`, then:
   ```bash
   vagrant-vmware-utility certificate generate
   vagrant-vmware-utility service install
   ```
   The service install step requires `sudo`.
5. No cloud credentials needed

### Raspberry Pi / ARM metal

The Pi is wired in as `provider: raspberry-pi`, `kind: metal` — a first-class target alongside the VM-oriented runtimes (`local-virtualbox`, `local-vmware`, `truenas`), but with a simpler lifecycle: there is nothing to "create" or "destroy" remotely. You flash the SD card by hand once, then the repo SSHs in to do the rest.

Recommended shape:

- Use the Pi as a persistent ARM sandbox host running one main Linux install.
- Let this repo manage first-boot/bootstrap and post-boot workload provisioning.
- Reserve VM-host orchestration for x86/TrueNAS when you need stronger guest isolation or x86 compatibility.

#### Required env vars

Set in `.env.local`:

- `RASPBERRY_PI_HOST` — e.g. `rapi.local` or the Pi's LAN IP
- `VM_USER_NAME` — the username preseeded into the SD card image (see Imager step below)
- `SSH_PUBLIC_KEY_FILE` — path to the public key whose private half is loaded in your agent

These are validated at runtime by [scripts/env-require](scripts/env-require) — `make ssh INSTANCE=<rpi-instance>` errors clearly if any are missing.

#### Initial SD card image (first boot)

Flash **Ubuntu Server 26.04 LTS (64-bit)** with the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Use Server (not Desktop) so the install stays reproducible — provisioning installs the GUI / Sunshine / etc. afterward, matching the Vagrant flow.

In Imager's advanced options (gear icon), preseed:

- **Hostname**: e.g. `rpi5`
- **Username**: `terraform` — matches `ssh_user` for the other remote-provisioned instances ([config/catalog.yaml](config/catalog.yaml)) so the Pi doesn't introduce a third naming convention.
- **Password**: a long throwaway. Provisioning enforces `PasswordAuthentication no`, so it only matters until first SSH-in.
- **SSH**: enabled, "Allow public-key authentication only", paste your public key.
- **Wi-Fi**: optional; fine for first boot / provisioning. Prefer **Ethernet** for actual streaming — Sunshine over Wi-Fi tends to surface as jitter and frame drops well before bandwidth is the bottleneck.

After flashing, boot the Pi, wait ~30s for it to come up, then verify reachability before pointing provisioning at it:

```bash
ssh terraform@rpi5.local      # mDNS on the LAN; over VPN, use the LAN IP or a real DNS record
```

See: [docs/raspberry-pi-provider.md](docs/raspberry-pi-provider.md)

## Local DNS / OpenVPN DNS (single hostname recommended)

Use one canonical hostname everywhere (LAN + VPN), for example:

- `truenas.home.arpa` -> `192.168.0.52`

Recommended setup:

1. **Router or DNS server record**
   - Add local DNS record: `truenas.home.arpa -> 192.168.0.52`
2. **OpenVPN DNS push**
   - Ensure your VPN server pushes the same DNS server/domain so this hostname resolves when remote.
3. **Repo env fallback (no root required)**
   - If DNS is not available, set `TRUENAS_HOST=192.168.0.52` in `.env.local`.

```bash
# .env.local
TRUENAS_HOST=truenas.home.arpa
TRUENAS_SSH_PORT=22
TRUENAS_SSH_USER=terraform
```

Provider connectivity summary:

```bash
make providers.status
```

## SSH config

```
Host vultr
  User Administrator
  HostName xxx.xxx.xxx.xxx
  UseKeychain yes
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_xxx
  ServerAliveInterval 10
```

## License

MIT — see [LICENSE](LICENSE).
