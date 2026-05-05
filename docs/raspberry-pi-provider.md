# Raspberry Pi Provider Notes

## Why this fits the repo

The current v2 catalog already separates:

- machine/provider runtime
- OS image
- init/bootstrap
- workload bundles

That model maps well to a Raspberry Pi, but the Pi should not be forced into the same shape as the existing VM-first providers.

For this repo, the cleanest interpretation is:

- `provider: raspberry-pi`
- `kind: metal`

That makes the Pi a first-class target alongside `aws`, `vultr`, `truenas`, `local-virtualbox`, and `local-vmware`, while acknowledging that its lifecycle is different.

## Recommended role

The best fit for a Raspberry Pi in this project is a persistent ARM sandbox host:

- one main Linux install on the Pi
- remote bootstrap and post-boot provisioning from this repo
- Docker/dev workloads installed via bundle-aware provisioning
- optional reprovision/reset workflow, but not full disposable VM semantics on day one

This is a better match than treating the Pi as:

- a TrueNAS-style VM provider
- a Vagrant-style local hypervisor
- a cloud-style fully ephemeral machine source

## Proposed catalog shape

Example future entries:

```yaml
machines:
  - name: raspberry-pi-5-dev
    provider: raspberry-pi
    kind: metal
    defaults:
      ssh_port: 22
      ssh_user: ubuntu
      architecture: arm64
      connection_mode: ssh

oses:
  - id: ubuntu-26.04-server-arm64
    family: ubuntu
    version: "26.04"
    arch: arm64
    ui_mode: headless

inits:
  - id: ssh-ubuntu-metal
    os_family: ubuntu
    provider: raspberry-pi
    features: [ssh, hardening, nonroot-user]

locations:
  - name: home-lan
    raspberry-pi:
      host: rpi5.home.arpa
      ssh_port: 22
      ssh_user: ubuntu

profiles:
  - name: rpi-ubuntu-dev-headless
    machine: raspberry-pi-5-dev
    os: ubuntu-26.04-server-arm64
    init: ssh-ubuntu-metal
    bundles: [access-headless, dev-sandbox-core]
    location: home-lan
```

## Lifecycle expectations

Unlike the existing cloud/VM providers, a Raspberry Pi target should start with simpler lifecycle semantics.

Reasonable first version:

- `profile.validate`
  - verify catalog compatibility
  - verify SSH reachability
  - verify remote OS family/arch if available
- `profile.plan`
  - resolve profile
  - show what provisioning and configuration would change
- `profile.apply`
  - bootstrap the host if needed
  - upload/run provisioning
  - optionally apply host-level config
- `profile.destroy`
  - remove managed workloads/config where safe
  - not necessarily destroy the machine itself

In other words, `destroy` for `kind: metal` should mean "tear down managed state" rather than "delete the host."

## Why this is useful

This lets the repo support a practical homelab/dev path:

- AWS/Vultr for ephemeral cloud machines
- TrueNAS for x86 LAN VMs
- Raspberry Pi for a low-risk ARM sandbox host

That is consistent with the repo's move from gaming-only infrastructure to a general machine-composition platform.

## Good workload fit

Good candidates for Raspberry Pi profiles here:

- `dev-sandbox-core`
- Docker-based experimentation
- OpenCode or similar CLI/dev-agent environments
- lightweight self-hosted services

Less ideal as an initial target:

- Windows workloads
- GPU-heavy gaming/streaming profiles
- assumptions that all providers support disposable VM lifecycle

## Recommended implementation order

1. Add catalog support for `provider: raspberry-pi` and `kind: metal`.
2. Add a provider-specific `init` entry such as `ssh-ubuntu-metal`.
3. Reuse the existing Linux provisioning runner in `linux/provision/`.
4. Make `profile.apply` for Raspberry Pi primarily an SSH/bootstrap/provision flow.
5. Add optional reset/cleanup semantics later if the repo gains image-based reinstallation workflows.

## Design guardrails

- Do not force Raspberry Pi into VM-only assumptions.
- Do not require full cloud-init image lifecycle before supporting it.
- Keep bundle/package compatibility rules shared with other Ubuntu targets.
- Model provider differences explicitly in the machine/init layer, not in workload bundles.

## Practical takeaway

For this repo, Raspberry Pi should be documented and eventually implemented as a metal ARM provider for persistent sandboxes, not as a substitute for the existing TrueNAS VM flow.
