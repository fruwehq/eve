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

v3 introduces concrete local instances on top of reusable recipes. Recipes still
come from the existing catalog entries, while concrete instances live in the
git-ignored local registry at `.egame/instances.yaml`.

```bash
# List reusable recipes
make recipes.list

# Create a concrete instance entry
make instance.create NAME=dev-a RECIPE=local-vmware-ubuntu-dev-gui DISK_GB=120 MEMORY_MB=12288 PACKAGES=xpra

# List and inspect concrete instances
make instance.list
make instance.info INSTANCE=dev-a
make instance.env INSTANCE=dev-a
make instance.paths INSTANCE=dev-a
make instance.state INSTANCE=dev-a
make instance.validate INSTANCE=dev-a

# Run existing profile-oriented targets through a generated instance overlay
make init INSTANCE=dev-a
make env INSTANCE=dev-a
make ssh INSTANCE=dev-a

# Inspect plugin contracts and package lifecycle hooks
make plugins.list
make provider.status INSTANCE=dev-a
make package.list INSTANCE=dev-a
make package.status INSTANCE=dev-a PACKAGE=docker
make package.down INSTANCE=dev-a PACKAGE=docker YES=1
```

The current v3 slice resolves concrete instances while preserving the existing
provider execution layer. `INSTANCE=` works by generating a local profile
overlay under `.generated/instances/<name>/` and reusing the profile-backed
scripts through provider plugins. Terraform-backed instances now get
instance-scoped backend roots and `TF_DATA_DIR` paths under
`.generated/instances/<name>/tf/`, so multiple concrete instances on the same
provider do not share local Terraform state.

Providers and packages are now described by plugin manifests. Built-ins live in
`plugins/providers/<id>/egame-plugin.yaml` and
`plugins/packages/<id>/egame-plugin.yaml`; optional external plugins can be
pinned in `.egame/plugin-sources.yaml` and synchronized with
`make plugins.sync`. Package `down` and `reinstall` operations are explicit and
destructive removals require `YES=1`.

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

## v2 profile workflow

Profiles are defined in `config/catalog.yaml` and resolved by `scripts/profile-resolve`.

Terraform provider versions are pinned exactly in the Terramate provider templates for reproducibility.

### Fresh checkout expectations

- Local profile paths (e.g. VirtualBox/Vagrant) should work without cloud API keys.
- Cloud providers (AWS/Vultr/TrueNAS) only require their own env vars when used.
- Keep personal settings in `.env.local`.

```bash
# List available profiles
make profiles.list

# Pick a profile interactively
make profiles.menu

# Targets without PROFILE=… will prompt you to pick one
make validate
make plan
```

Local customizations (without git-dirty state):

```bash
cp config/catalog.local.example.yaml config/catalog.local.yaml
# edit config/catalog.local.yaml for personal overrides
```

`config/catalog.local.yaml` is git-ignored and merged over the base catalog.

```bash
# Validate and inspect a profile
make validate PROFILE=aws-ubuntu-dev-headless
make info PROFILE=aws-ubuntu-dev-headless

# Cloud profile (terraform engine)
make init PROFILE=aws-ubuntu-dev-headless
make plan PROFILE=aws-ubuntu-dev-headless
make up PROFILE=aws-ubuntu-dev-headless
make provision PROFILE=aws-ubuntu-dev-headless  # installs bundle packages on the VM
make ssh PROFILE=aws-ubuntu-dev-headless
make down PROFILE=aws-ubuntu-dev-headless

# Local profile (vagrant engine)
make plan PROFILE=local-vbox-ubuntu-dev
make up PROFILE=local-vbox-ubuntu-dev
make down PROFILE=local-vbox-ubuntu-dev

# TrueNAS profile (real provider wiring)
make validate PROFILE=truenas-ubuntu-dev-headless
make info PROFILE=truenas-ubuntu-dev-headless

# Required env vars for provider auth:
# - TRUENAS_SSH_PRIVATE_KEY_FILE (path to private key)
# - TRUENAS_SSH_HOST_KEY_FINGERPRINT (e.g., SHA256:...)
# Optional: host/user/port from .env.local (TRUENAS_HOST/TRUENAS_SSH_USER/TRUENAS_SSH_PORT)

# Example (macOS/Linux):
# export TRUENAS_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/truenas_ed25519"
# export TRUENAS_SSH_HOST_KEY_FINGERPRINT="SHA256:..."

make init PROFILE=truenas-ubuntu-dev-headless
make plan PROFILE=truenas-ubuntu-dev-headless
make up PROFILE=truenas-ubuntu-dev-headless
make down PROFILE=truenas-ubuntu-dev-headless
```

## Post-boot provisioning (Linux + Windows)

After `up` creates an instance, run `provision` to install bundle packages:

```bash
make ssh.wait PROFILE=aws-ubuntu-dev-headless   # optional — wait for SSH
make provision PROFILE=aws-ubuntu-dev-headless  # installs bundles
make logs PROFILE=aws-ubuntu-dev-headless       # tail remote logs
```

`make provision` dispatches by the profile's `os_family`:

- Linux: uploads [linux/provision/](linux/provision/) to `$HOME/provision` on the VM, installs a `systemd` unit, and runs numbered steps (`00_base`, `10_docker`, `20_dev-toolchain`, `30_codex-cli`, `40_goose`, `45_xpra`, `50_rustdesk`, `60_sunshine`, `70_steam`, `99_finish`). Each step is skipped if its package id is not in the profile's bundles.
- Windows: uploads [windows/provision/](windows/provision/) to `C:\Users\Administrator\provision` and runs `bootstrap.ps1`, which registers a Scheduled Task that walks a similar sorted `steps/` directory. Requires `EPHEMERAL_WINDOWS_PASSWORD` (or a terraform output) and `EPHEMERAL_SUNSHINE_PASSWORD` — used to build `./tmp/env.json` and scp it into the provision state dir.

State is tracked in `$HOME/provision/state/state.json` on the VM — provisioning resumes from the last completed step after a reboot.

## Remote GUI apps via Xpra (no full desktop)

Xpra forwards individual remote applications over SSH and renders them as native-looking windows on the local host — useful when you want one remote app (e.g. a browser, IDE, or X11 tool) without pulling up a full remote desktop. Xpra is bundle-gated by the `remote-apps` bundle, so it is only installed on profiles that opt in.

> Linux profiles use virtual displays (`xpra start :N`). Windows profiles use shadow mode via Scheduled Task + SSH tunnel.

### Local install (macOS)

1. **XQuartz** (X11 server) — `brew install --cask xquartz` (log out/in after first install).
2. **Xpra client** — install the **official signed `.pkg` from [xpra.org/install](https://xpra.org/install/)** (also linked from the project's [GitHub wiki](https://github.com/Xpra-org/xpra/wiki/Download)).

   > Do **not** use `brew install --cask xpra`. The Homebrew cask is deprecated (fails macOS Gatekeeper, scheduled for removal on 2026-09-01). The upstream `.pkg` is code-signed and notarized by the Xpra project.

### Local install (Linux)

```bash
sudo apt-get install xpra          # Debian/Ubuntu
# or follow https://github.com/Xpra-org/xpra/wiki/Download for other distros
```

### Enable on a profile

Add the `remote-apps` bundle to the profile in `config/catalog.yaml` (or your `catalog.local.yaml`):

```yaml
profiles:
  - name: aws-ubuntu-dev-headless
    machine: aws-cheap-x86
    os: ubuntu-24.04-server-amd64
    init: ssh-ubuntu-cloud-init
    bundles: [access-headless, dev-sandbox-core, remote-apps]
    location: tokyo
```

Then re-run `make provision PROFILE=…` to install `xpra` on the VM.

### Launch an app

```bash
make remote.xpra PROFILE=aws-ubuntu-dev-headless APP=xeyes          # smoke test
make remote.xpra PROFILE=aws-ubuntu-dev-headless APP=firefox        # browser
make remote.xpra PROFILE=aws-ubuntu-dev-headless APP="xterm -e htop"
```

The target starts an Xpra server on the VM, launches the requested app, and attaches a local client window. Use `make remote.xpra.stop PROFILE=...` to stop the remote session.

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

### VirtualBox (local, Apple Silicon ⚠️)

> **Note**: VirtualBox on Apple Silicon (M1/M2/M3/M4) has limited ARM64 VM support and may fail to boot. VMware Fusion is recommended instead.

1. **VirtualBox** — [install](https://www.virtualbox.org/wiki/Downloads) (version 7.1+)
2. **Vagrant** — `brew install hashicorp/tap/vagrant`
3. No cloud credentials needed

### VMware Fusion (local, Apple Silicon ✅)

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

These are validated at runtime by [scripts/env-require](scripts/env-require) — `make ssh PROFILE=rpi-ubuntu-all` errors clearly if any are missing.

#### Initial SD card image (first boot)

Flash **Ubuntu Server 24.04 LTS (64-bit)** with the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Use Server (not Desktop) so the install stays reproducible — provisioning installs the GUI / Sunshine / etc. afterward, matching the Vagrant flow.

In Imager's advanced options (gear icon), preseed:

- **Hostname**: e.g. `rpi5`
- **Username**: `terraform` — matches `ssh_user` for the other remote-provisioned profiles ([config/catalog.yaml](config/catalog.yaml)) so the Pi doesn't introduce a third naming convention.
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
