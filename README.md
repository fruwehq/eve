# v2: Profile-Driven VM Platform

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

## v2 profile workflow (new)

Profiles are defined in `config/catalog.yaml` and resolved by `scripts/profile-resolve`.

Terraform provider versions are pinned exactly in the Terramate provider templates for reproducibility.

### Fresh checkout expectations

- Local profile paths (e.g. VirtualBox/Vagrant) should work without cloud API keys.
- Cloud providers (AWS/Vultr/TrueNAS) only require their own env vars when used.
- Keep personal settings in `.env.local`.

```bash
# List available profiles
make profiles.list

# Pick a profile interactively (also auto-prompts if PROFILE is unset)
make profiles.menu

# default PROFILE is local-vbox-ubuntu-dev
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
make apply PROFILE=aws-ubuntu-dev-headless
make provision PROFILE=aws-ubuntu-dev-headless  # installs bundle packages on the VM
make ssh PROFILE=aws-ubuntu-dev-headless
make destroy PROFILE=aws-ubuntu-dev-headless

# Local profile (vagrant engine)
make plan PROFILE=local-vbox-ubuntu-dev
make apply PROFILE=local-vbox-ubuntu-dev
make destroy PROFILE=local-vbox-ubuntu-dev

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
make apply PROFILE=truenas-ubuntu-dev-headless
make destroy PROFILE=truenas-ubuntu-dev-headless
```

## Post-boot provisioning (Linux + Windows)

After `apply` creates an instance, run `provision` to install bundle packages:

```bash
make ssh.wait PROFILE=aws-ubuntu-dev-headless   # optional — wait for SSH
make provision PROFILE=aws-ubuntu-dev-headless  # installs bundles
make logs PROFILE=aws-ubuntu-dev-headless       # tail remote logs
```

`make provision` dispatches by the profile's `os_family`:

- Linux: uploads [linux/provision/](linux/provision/) to `$HOME/provision` on the VM, installs a `systemd` unit, and runs numbered steps (`00_base`, `10_docker`, `20_dev-toolchain`, `30_codex-cli`, `40_goose`, `45_xpra`, `50_rustdesk`, `60_sunshine`, `70_steam`, `99_finish`). Each step is skipped if its package id is not in the profile's bundles.
- Windows: uploads [windows/provision/](windows/provision/) to `C:\Users\Administrator\provision` and runs `bootstrap.ps1`, which registers a Scheduled Task that walks a similar sorted `steps/` directory. Requires `EPHEMERAL_WINDOWS_PASSWORD` (or a terraform output) and `EPHEMERAL_SUNSHINE_PASSWORD` — used to build `./tmp/secrets.json` and scp it into the provision state dir.

State is tracked in `$HOME/provision/state/state.json` on the VM — provisioning resumes from the last completed step after a reboot.

## Remote GUI apps via Xpra (no full desktop)

Xpra forwards individual remote Linux applications over SSH and renders them as native-looking windows on the local host — useful when you want one remote app (e.g. a browser, IDE, or X11 tool) without pulling up a full remote desktop. Xpra is bundle-gated by the `remote-apps` bundle, so it is only installed on profiles that opt in.

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
make xpra PROFILE=aws-ubuntu-dev-headless APP=xeyes          # smoke test
make xpra PROFILE=aws-ubuntu-dev-headless APP=firefox        # browser
make xpra PROFILE=aws-ubuntu-dev-headless APP="xterm -e htop"
```

The first invocation will spawn an Xpra server on the VM, tunnel it over SSH, and attach a local client window. Closing the app exits the Xpra session (`--exit-with-children`).

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
4. **Required env vars** (in `.env.local`):
   - `TRUENAS_HOST` — e.g. `192.168.0.52` or `truenas.home.arpa`
   - `TRUENAS_SSH_USER` — e.g. `terraform`
   - `TRUENAS_SSH_PRIVATE_KEY_FILE` — path to private key
   - `TRUENAS_SSH_HOST_KEY_FINGERPRINT` — e.g. `SHA256:...`
   - `TRUENAS_API_KEY` — REST API key for cloud-init ISO upload
5. **Optional env vars** (defaults in `.env`, override in `.env.local`):
   - `TRUENAS_SSH_PORT` (default: `22`)
   - `TRUENAS_VM_ISO_DIR` (default: `/mnt/main/iso`) — path on TrueNAS where cloud-init ISOs are stored
6. **One-time disk setup** — write the Ubuntu 24.04 cloud image to the zvol before first boot:
   ```bash
   # On TrueNAS (after apply creates the zvol):
   curl -O https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img
   dd if=ubuntu-24.04-server-cloudimg-amd64.img of=/dev/zvol/main/vms/truenasubuntudevheadless bs=4M
   ```
7. **Network**: must be reachable (LAN or VPN)

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

### Raspberry Pi / ARM metal (planned)

This repo's current local runtimes are VM-oriented (`local-virtualbox`, `local-vmware`, `truenas`).
For a Raspberry Pi, the better fit is a future `provider: raspberry-pi` machine entry with `kind: metal` rather than trying to force the Pi into a VM-host role.

Recommended shape:

- Use the Pi as a persistent ARM sandbox host running one main Linux install.
- Let this repo manage first-boot/bootstrap and post-boot workload provisioning.
- Reserve VM-host orchestration for x86/TrueNAS when you need stronger guest isolation or x86 compatibility.

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
