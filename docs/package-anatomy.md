# Anatomy of an eve package

A package plugin has **two execution contexts**. Keeping them in separate
directories is intentional — they run in different places, as different users,
with different invocation models.

```
my-package/
  eve-plugin.yaml          # manifest: id, supports, commands, install, bundles
  commands/                # HOST-side dispatch entrypoints
    ubuntu/{status,down}   #   run on YOUR machine by eve (portable sh)
    windows/{status,down}  #   they remote-exec a quick query/op on the instance
  provision/               # GUEST-side install steps
    ubuntu/<pkg>.sh        #   run ON the instance during install (bash)
    windows/<pkg>.ps1      #   run ON the instance during install (PowerShell)
```

## `commands/` — host-side, lightweight

`commands/<os>/<verb>` are executed by eve **on the host** (your Mac/Linux box).
They are `#!/usr/bin/env sh` because they run wherever eve runs and typically do
one thing: open an SSH/WinRM session and run a short query or teardown. `status`
and `down` live here — they are one-shot lifecycle operations on an
already-installed package, not provisioning.

## `provision/` — guest-side, staged

`install` does **not** have a `commands/` entry. It flows through the
provisioning pipeline declared in the manifest's `install.<os_family>.steps`,
which uploads the `provision/<os>/` tree and runs the steps **on the instance**.
This is why install scripts are `provision/ubuntu/<pkg>.sh` (bash on the guest)
or `provision/windows/<pkg>.ps1` (PowerShell on the guest): they run in the
guest's native shell, and the pipeline is staged and reboot/state-aware.

## Why the split (and why `status` isn't "odd")

| | `commands/` | `provision/` |
| --- | --- | --- |
| Runs on | the host | the instance (guest) |
| Shell | portable `sh` | guest-native (`sh`/`ps1`) |
| Model | one-shot op | staged pipeline |
| Used by | `status`, `down`, actions | `install` |

`install` is heavy (multi-step, reboots, state) → pipeline. `status`/`down` are
quick remote checks → host commands. Folding the latter into the provisioning
pipeline would over-engineer one-shot operations.

## Manifest essentials

```yaml
api_version: eve.plugin/v1
kind: package
id: my-package
display_name: My Package
supports: {os_families: [ubuntu]}        # or [windows], or both (dual-OS)
commands:
  status: {exec: commands/ubuntu/status, args: [my-package]}
  down:   {exec: commands/ubuntu/down,   args: [my-package]}
install:
  ubuntu:
    steps: [base.sh, provision/ubuntu/my-package.sh]
depends_on: [other-package]               # optional: expanded deps-first
bundles:                                   # optional: package-owned bundles
  - id: my-bundle
    includes: [my-package, other-package]
```

Validate with `eve plugin test ./my-package`. Scaffold a new repo from
[`eve-plugin-template`](https://github.com/fruwehq/eve-plugin-template).
