# v3: Instance-Driven VM Platform

> Work in progress: this repo is evolving from gaming-only infra into a layered machine-composition platform (machine + OS + init + workloads), supporting cloud and local targets.
>
> See: [docs/multi-purpose-vm-blueprint.md](docs/multi-purpose-vm-blueprint.md)
>
> Next boundary cleanup: [docs/v3.1-provider-plugin-boundaries-plan.md](docs/v3.1-provider-plugin-boundaries-plan.md)
>
> Planned runtime notes: [docs/raspberry-pi-provider.md](docs/raspberry-pi-provider.md)
>
> Remote desktop compatibility matrix:
> [docs/remote-desktop-compatibility.md](docs/remote-desktop-compatibility.md)

## Quickstart on macOS

```bash
brew install jq poetry python@3.14 shellcheck sshpass yq
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

TERRAMATE_VERSION=0.17.0
case "$(uname -m)" in
  arm64|aarch64) TERRAMATE_ARCH=arm64 ;;
  x86_64|amd64) TERRAMATE_ARCH=x86_64 ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 2 ;;
esac
curl -fsSLo /tmp/terramate.tar.gz "https://github.com/terramate-io/terramate/releases/download/v${TERRAMATE_VERSION}/terramate_${TERRAMATE_VERSION}_darwin_${TERRAMATE_ARCH}.tar.gz"
mkdir -p /tmp/terramate
tar -C /tmp/terramate -xzf /tmp/terramate.tar.gz
sudo find /tmp/terramate -type f -name terramate -exec install -m 0755 {} /usr/local/bin/terramate \; -quit

poetry env use python3.14
poetry install
make doctor
make eve
```

On first launch, `FirstRunScreen` lists missing required provider fields.
Settings are stored through v3.2's `.eve/config.yaml` and
`.eve/secrets/<provider>.yaml` flow; see
[Fresh checkout expectations](#fresh-checkout-expectations).

## Quickstart on Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg jq make openssh-client ripgrep shellcheck software-properties-common sshpass unzip yq

sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y --no-install-recommends python3.14 python3.14-dev python3.14-venv
curl -sSL https://install.python-poetry.org | python3.14 -
export PATH="$HOME/.local/bin:$PATH"

. /etc/os-release
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${VERSION_CODENAME} main" | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
sudo apt-get update
sudo apt-get install -y --no-install-recommends terraform

TERRAMATE_VERSION=0.17.0
case "$(uname -m)" in
  arm64|aarch64) TERRAMATE_ARCH=arm64 ;;
  x86_64|amd64) TERRAMATE_ARCH=x86_64 ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 2 ;;
esac
curl -fsSLo /tmp/terramate.tar.gz "https://github.com/terramate-io/terramate/releases/download/v${TERRAMATE_VERSION}/terramate_${TERRAMATE_VERSION}_linux_${TERRAMATE_ARCH}.tar.gz"
mkdir -p /tmp/terramate
tar -C /tmp/terramate -xzf /tmp/terramate.tar.gz
sudo find /tmp/terramate -type f -name terramate -exec install -m 0755 {} /usr/local/bin/terramate \; -quit

poetry env use python3.14
poetry install
make doctor
make eve
```

On first launch, `FirstRunScreen` lists missing required provider fields.
Settings are stored through v3.2's `.eve/config.yaml` and
`.eve/secrets/<provider>.yaml` flow; see
[Fresh checkout expectations](#fresh-checkout-expectations).

## Quickstart with Docker

```bash
docker run -it -v ~/.eve-data:/data eve/eve:slim make eve
```

The v3.3 slim image is capped at a 500 MB compressed pull/archive size; expect
the download to be roughly in the mid-400 MB range.

```bash
docker run -it \
  -v "$HOME/.eve-data:/data" \
  -v "$HOME/.ssh:/root/.ssh:ro" \
  -v "$SSH_AUTH_SOCK:/ssh-agent" \
  -e SSH_AUTH_SOCK=/ssh-agent \
  eve/eve:slim make eve
```

The container forwards your host's ssh-agent so SSH operations against
provisioned instances use keys held on the host (the keys never enter the
container image). Ensure your agent is running and has your keys loaded before
launching:

```bash
ssh-add -l    # should list at least one key; if not, start an agent and ssh-add your key
```

If `SSH_AUTH_SOCK` is unset, `docker compose` will refuse to start with a clear
error pointing here.

```bash
export SSH_AUTH_SOCK="${SSH_AUTH_SOCK:?start ssh-agent or export SSH_AUTH_SOCK first}"
docker compose run --rm eve make eve
```

The runtime image has Eve baked into `/opt/eve` and defaults `EVE_HOME` to
`/data`, so `.eve/` state and `.generated/` artifacts persist in the mounted
host directory. The second command adds SSH keys and SSH agent forwarding for
provider operations. On first launch, `FirstRunScreen` lists missing required
provider fields; settings are stored through v3.2's `.eve/config.yaml` and
`.eve/secrets/<provider>.yaml` flow.

## v3 instance workflow

v3 introduces concrete local instances selected from provider/platform catalog
choices. Instances live in the git-ignored local registry at
`.eve/instances.yaml`.

```bash
# List supported provider / platform / content choices
make catalog.list

# Create a concrete instance entry
make instance.create INSTANCE=dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=desktop-streaming DISK_GB=32

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
# or
make eve

# Run lifecycle targets through the selected concrete instance
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
init methods, locations, bundles, packages, and plugins; `.eve/instances.yaml`
defines concrete local instances composed from those catalog entries. Provider
and package plugins receive resolved instance JSON, and legacy profile-shaped
overlays are generated only as an internal compatibility detail for lower-level
provider scripts.

The built-in Linux Docker package installs Docker in rootless mode. The daemon
runs as the VM user through `systemd --user`, and `DOCKER_HOST` points at the
user socket under `/run/user/<uid>/docker.sock`.

Experimental Wayland app forwarding is available through the `waypipe` package
and the `desktop-streaming` bundle. Waypipe is only the transport/proxy: on
macOS it also needs a local Wayland compositor to render the remote window.
XQuartz only provides X11, so `DISPLAY=/.../org.xquartz:0` is not enough.

```bash
make package.select INSTANCE=dev-a PACKAGE=waypipe
make package.install INSTANCE=dev-a PACKAGE=waypipe
```

Recommended macOS experiment: **Cocoa-Way + waypipe-darwin**.

1. Install the local compositor and Waypipe transport on the Mac:

   ```bash
   brew tap J-x-Z/tap
   brew install cocoa-way waypipe-darwin
   ```

2. Start Cocoa-Way in one terminal and keep it running:

   ```bash
   cocoa-way
   ```

3. In another Mac terminal, point Waypipe at Cocoa-Way's socket:

   ```bash
   export XDG_RUNTIME_DIR="$(find /var/folders /tmp -type d -name cocoa-way 2>/dev/null | head -n 1)"
   export WAYLAND_DISPLAY=wayland-1
   echo "$XDG_RUNTIME_DIR"
   ls -l "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
   ```

   The last command should show a socket such as
   `/.../cocoa-way/wayland-1`. If it does not, Cocoa-Way is not running or the
   socket directory was not found.

4. Install a tiny Wayland test app on the remote Linux instance:

   ```bash
   make package.select INSTANCE=dev-a PACKAGE=waypipe
   make package.install INSTANCE=dev-a PACKAGE=waypipe
   ```

   Or manually on Ubuntu/Debian:

   ```bash
   sudo apt update
   sudo apt install -y waypipe zenity
   ```

5. Run the first hello-world test from the Mac terminal that exported
   `XDG_RUNTIME_DIR` and `WAYLAND_DISPLAY`:

   ```bash
   waypipe --no-gpu ssh -o StreamLocalBindUnlink=yes user@remote-host \
     env GDK_BACKEND=wayland zenity --info --text="Hello Waypipe"
   ```

   `StreamLocalBindUnlink=yes` helps when stale local socket files otherwise
   cause "remote port forwarding failed" errors. `--no-gpu` is useful when a
   window opens black, crashes, or behaves strangely; remove it after the small
   test works.

6. Try a Weston sample or a real app:

   ```bash
   sudo apt install -y weston
   waypipe ssh -o StreamLocalBindUnlink=yes user@remote-host weston-flower

   waypipe ssh -o StreamLocalBindUnlink=yes user@remote-host \
     env GDK_BACKEND=wayland gedit
   waypipe --no-gpu ssh -o StreamLocalBindUnlink=yes user@remote-host \
     env GDK_BACKEND=wayland gedit
   ```

The repo action uses the same local compositor requirement:

```bash
make package.action INSTANCE=dev-a PACKAGE=waypipe ACTION=waypipe APP=foot
```

Wawona and wprs are still interesting research paths, but they are not the
recommended first macOS setup today.

This is a trial path, not a stable replacement for Xpra yet. For reliable
day-to-day Linux GUI access on macOS, prefer RustDesk, VNC, Sunshine/Moonlight,
or Xpra where the OS/package source supports it.

Terraform-backed instances get instance-scoped backend roots and `TF_DATA_DIR` paths under
`.generated/instances/<name>/tf/`, so multiple concrete instances on the same
provider do not share local Terraform state.

Linux GUI packages are selected explicitly through bundles and packages.
For GNOME trials, select `gnome-desktop`; adding `macos-desktop-theme` applies a
best-effort dock-at-bottom, left-side window controls, dark color scheme, and
Papirus icon setup on the next GNOME login.

Providers and packages are now described by plugin manifests. Built-ins live in
`plugins/providers/<id>/eve-plugin.yaml` and
`plugins/packages/<id>/eve-plugin.yaml`; optional external plugins can be
pinned in `.eve/plugin-sources.yaml` and synchronized with
`make plugins.sync`. Package `down` and `reinstall` operations are explicit and
destructive removals require `YES=1`.

Plugin contracts and example external plugin layouts are documented in
[docs/plugins.md](docs/plugins.md).

Instance state contracts are documented in [docs/state.md](docs/state.md).

Manual and AI-assisted live test flow is documented in
[docs/integration-testing.md](docs/integration-testing.md). Start with
`make integration.plan INSTANCES=<linux>,<windows>`; live runs require
`YES=1 make integration.test INSTANCES=<linux>,<windows>`. For a heavier
package sweep, use
`YES=1 make integration.packages INSTANCES=<linux>,<windows>` to install and
status-check every installable package supported by each instance OS/arch.
The optional `make eve` target opens **Eve** (Ephemeral VM Environment), a
Textual instance manager for browsing instances, combined state, package state,
and safe provider/package actions. `make tui` remains available as a
compatibility alias.
Run `make install-cli` once to install an `eve` command into `~/.local/bin`;
after that, `eve` opens the same TUI from any directory as long as
`~/.local/bin` is on your `PATH`.
Use `poetry install` once to install the Python command and TUI dependencies.

### Optional containerized toolchain

```bash
make docker.runtime.slim
make docker.runtime.full
make docker.build
make docker.shell
make docker.test
```

The v3.3 runtime images bake the repository into `/opt/eve` and default
`EVE_HOME` to `/data`. `eve/eve:slim` is the cloud-provider runtime;
`eve/eve:full` adds Vagrant and QEMU for local-qemu work. The older
`docker.build` target remains as a contributor toolchain image for shelling
into the checkout and running tests.

On Linux hosts, `make test` includes the slim runtime Docker smoke by default.
CI sets `EVE_SKIP_DOCKER_SMOKE=1` in the Ubuntu host job because the required
`docker-runtime-slim` job owns the build, smoke, and image-size checks there.

Package plugins may provide host-side command hooks at
`commands/<os_family>/<install|status|down>` or
`commands/common/<install|status|down>`. The built-in compatibility wrapper
passes the resolved instance JSON on stdin and sets `EVE_INSTANCE_NAME`,
`EVE_PACKAGE_PLUGIN`, and `EVE_PACKAGE_PLUGIN_ROOT`.

Manifest command `exec` paths may point at core repo scripts, such as
`scripts/package-plugin`, or at plugin-local executables. External plugins that
reuse a built-in id are rejected by default; set `EVE_PLUGIN_ALLOW_OVERRIDE=1`
only when you intentionally want the later external plugin to replace the
built-in one.

`make instance.paths INSTANCE=<name>` shows the generated overlay path,
instance state file path, and Terraform artifact roots used by the bridge.

## Instance Workflow

Terraform provider versions are pinned exactly in the Terramate provider templates for reproducibility.

### Fresh checkout expectations

- Local instance choices (for example QEMU/Vagrant) should work without cloud API keys.
- Cloud providers (AWS/Vultr/TrueNAS) only require their own credentials when used.
- **Non-secret configuration lives in `.eve/config.yaml`** (structured, validated, TUI-editable).
- **Secrets live in `.eve/secrets/<provider>.yaml`** (mode 0600, gitignored).
- On first run, the TUI shows a `FirstRunScreen` listing missing required fields.
- Press `S` in the TUI to open Settings; click `Configure` on any provider row to edit provider-specific settings.
- `make doctor` checks which required fields are populated.
- The old `.env` / `.env.local` approach was removed in v3.2 — no existing users.

```bash
# List catalog choices and create a concrete instance
make catalog.list
make instance.create INSTANCE=dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=dev-ai

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
make instance.create INSTANCE=local-dev-a MACHINE=local-qemu-medium OS=ubuntu-26.04-arm64 LOCATION=tokyo BUNDLES=dev-ai
make plan INSTANCE=local-dev-a
make up INSTANCE=local-dev-a
make down INSTANCE=local-dev-a

# TrueNAS instance (real provider wiring)
make instance.create INSTANCE=truenas-dev-a MACHINE=truenas-scale-medium OS=ubuntu-26.04-amd64 LOCATION=tokyo BUNDLES=dev-ai
make validate INSTANCE=truenas-dev-a
make info INSTANCE=truenas-dev-a

# Required provider settings:
# - secrets.truenas.ssh_private_key_file (path to private key)
# - config.truenas.ssh_host_key_fingerprint (e.g., SHA256:...)
# Optional: config.truenas.host/config.truenas.ssh_user/config.truenas.ssh_port

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

- Linux: stages the shared provisioning runner plus selected package-local
  install steps, uploads them to `$HOME/provision` on the VM, installs a
  `systemd` unit, and runs numbered package steps. During the v3.1 migration,
  manifests may still reference legacy shared steps, but package-specific steps
  should live under `plugins/packages/<id>/provision/ubuntu/`.
- Windows: uploads [oses/windows-server-2025/provision/](oses/windows-server-2025/provision/) to `C:\Users\Administrator\provision` and runs `bootstrap.ps1`, which registers a Scheduled Task that walks a similar sorted `steps/` directory. Requires `EPHEMERAL_WINDOWS_PASSWORD` (or a terraform output) and `EPHEMERAL_SUNSHINE_PASSWORD` — used to build `./tmp/env.json` and scp it into the provision state dir.

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
- [jq](https://jqlang.github.io/jq/download/) — JSON processing for profile resolution (`brew install jq` on macOS)
- `make`

For managed Linux guests, set `global.vm_user_name` in Settings or export
`VM_USER_NAME` for the current shell. v3.1 no longer falls back to
image-default users such as `ubuntu` on normal orchestration paths; provider
init/cloud-init creates or enables the configured user, and later
SSH/provision/package commands use that identity.

### AWS

1. **AWS CLI** — [install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
2. **Authenticate** — run `aws login` (or `aws sso login`) to refresh credentials
3. **Configuration** (via TUI Configure screen, `.eve/config.yaml`, or env vars):
   - `aws.profile` / `AWS_PROFILE` — e.g. `hekk-dev`
   - `aws.region` / `AWS_REGION` — e.g. `ap-northeast-1`
4. **Secrets** (via TUI Configure screen, or `.eve/secrets/aws.yaml`):
   - `access_key_id` / `AWS_ACCESS_KEY_ID`
   - `secret_access_key` / `AWS_SECRET_ACCESS_KEY`

### GCP

1. **Google Cloud CLI** — [install](https://cloud.google.com/sdk/docs/install)
2. **Authenticate** — run `gcloud auth application-default login`, or export `GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"` when ADC has less access than your active user account.
3. **Configuration** (via TUI Configure screen, `.eve/config.yaml`, or env vars):
   - `gcp.project` / `GOOGLE_CLOUD_PROJECT` — optional if `gcloud config get-value project` is correct
4. **Secrets** (via TUI Configure screen, or `.eve/secrets/gcp.yaml`):
   - `application_credentials` / `GOOGLE_APPLICATION_CREDENTIALS`

### Vultr

1. **API key** — [generate one](https://my.vultr.com/settings/#settingsapi)
2. **Secrets** (via TUI Configure screen, or `.eve/secrets/vultr.yaml`):
   - `api_key` / `VULTR_API_KEY` (required)

### TrueNAS

1. **SSH key** — generate a keypair for Terraform to use
2. **TrueNAS user** — create a Terraform user with SSH access and `terraform` group
3. **API key** — generate one in TrueNAS → API Keys (used for cloud-init ISO upload)
4. **Configuration** (via TUI Configure screen, `.eve/config.yaml`, or env vars):
   - `truenas.host` / `TRUENAS_HOST` — e.g. `192.168.0.52` (required)
   - `truenas.ssh_user` / `TRUENAS_SSH_USER` — e.g. `terraform`
   - `truenas.ssh_port` / `TRUENAS_SSH_PORT` (default: `22`)
   - `truenas.api_user` / `TRUENAS_API_USER`
   - `truenas.ssh_host_key_fingerprint` / `TRUENAS_SSH_HOST_KEY_FINGERPRINT`
   - `truenas.vm_base_dir` / `TRUENAS_VM_BASE_DIR` — e.g. `/mnt/pool1/eve`
   - `truenas.vm_pool` / `TRUENAS_VM_POOL` — e.g. `pool1`
   - `truenas.vm_zvol_prefix` / `TRUENAS_VM_ZVOL_PREFIX` — e.g. `eve`
5. **Secrets** (via TUI Configure screen, or `.eve/secrets/truenas.yaml`):
   - `ssh_private_key_file` / `TRUENAS_SSH_PRIVATE_KEY_FILE` (required)
   - `api_key` / `TRUENAS_API_KEY`
6. **Optional SSH port**:
   - `truenas.ssh_port` / `TRUENAS_SSH_PORT` (default: `22`)
7. **One-time ZFS setup** — create the parent dataset:
    ```bash
    # On TrueNAS web UI: Storage > pool1 > Add Dataset (preset: Generic)
    #   Name: eve    →  creates pool1/eve
    ```
    The dataset (`pool1/eve`) must exist before `make up`. Subdirectories (`iso/`, `images/`) are created automatically.
8. **One-time sudoers setup** — the Terraform user needs `sudo dd` access to write cloud images to zvols. Add to sudoers (`visudo` on TrueNAS):
    ```
    terraform ALL=(ALL) NOPASSWD: /usr/bin/dd if=/mnt/pool1/eve/images/* of=/dev/zvol/pool1/eve/*
    ```
    Adjust path to `/bin/dd` if using TrueNAS CORE (FreeBSD).
9. **Disk image setup** — `make up` downloads the cloud image directly to the NAS, writes it to a zvol, and resizes the partition. No manual `dd` needed.

### QEMU (local, Apple Silicon ✅)

QEMU is the preferred local Linux provider on Apple Silicon. It uses the public
`cloud-image/ubuntu-26.04` Vagrant box with the `qemu` provider artifact.

1. **QEMU** — `brew install qemu`
2. **Vagrant** — `brew install hashicorp/tap/vagrant`
3. **Vagrant QEMU plugin** — `vagrant plugin install vagrant-qemu`
4. No cloud credentials needed

### Raspberry Pi / ARM metal

The Pi is wired in as `provider: raspberry-pi`, `kind: metal` — a first-class target alongside the VM-oriented runtimes (`local-qemu`, `truenas`, cloud providers), but with a simpler lifecycle: there is nothing to "create" or "destroy" remotely. You flash the SD card by hand once, then the repo SSHs in to do the rest.

Recommended shape:

- Use the Pi as a persistent ARM sandbox host running one main Linux install.
- Let this repo manage first-boot/bootstrap and post-boot workload provisioning.
- Reserve VM-host orchestration for x86/TrueNAS when you need stronger guest isolation or x86 compatibility.

#### Required config

Raspberry Pi instances use the same global SSH key config as every other
provider:

- `global.vm_user_name` / `VM_USER_NAME` — the username preseeded into the SD card image (see Imager step below)
- `global.ssh_public_key_file` / `SSH_PUBLIC_KEY_FILE` — path to the public key whose private half is loaded in your agent

The Pi address is instance-specific so multiple boards can be managed from one
registry. Create each Pi instance with its own `PROVIDER_IP`:

```sh
make instance.create INSTANCE=rpi5-a MACHINE=raspberry-pi-5 OS=ubuntu-26.04-arm64 LOCATION=tokyo PROVIDER_IP=192.168.0.41 BUNDLES=dev-ai
make instance.create INSTANCE=rpi5-b MACHINE=raspberry-pi-5 OS=ubuntu-26.04-arm64 LOCATION=tokyo PROVIDER_IP=192.168.0.42 BUNDLES=desktop-streaming
```

The TUI asks for this IP address when the selected platform is Raspberry Pi.
`raspberry_pi.host` / `raspberry_pi.ip` in `.eve/config.yaml` remain useful as
single-board defaults, but a per-instance `provider_config.ip` wins whenever it
is present.

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
3. **Repo config fallback (no root required)**
   - If DNS is not available, save the host in Eve config.

```bash
./scripts/config-save truenas host truenas.home.arpa
./scripts/config-save truenas ssh_port 22
./scripts/config-save truenas ssh_user terraform
```

Provider connectivity and configuration summary:

```bash
make doctor
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
