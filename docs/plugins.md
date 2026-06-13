# v3 Plugin Contracts

v3 keeps provider and package implementation details out of the core
orchestrator. Core scripts discover plugin manifests, validate their shape, and
dispatch commands with resolved instance JSON on stdin.

## Discovery

Built-in plugins live under:

- `plugins/providers/<id>/eve-plugin.yaml`
- `plugins/packages/<id>/eve-plugin.yaml`

External plugins may be synchronized into `.eve/plugins/<source-id>/` with:

```bash
make plugins.sync
```

Additional local roots can be tested without syncing:

```bash
EVE_PLUGIN_ROOTS=examples/plugins/packages/hello-package make plugins.validate
```

If two plugins use the same `kind:id`, validation fails unless
`EVE_PLUGIN_ALLOW_OVERRIDE=1` is set.

## Manifest Fields

Every manifest uses:

```yaml
api_version: eve.plugin/v1
kind: provider|package
id: example-id
display_name: Human Name
commands: {}
supports: {}
env: []
```

`id` must match `[a-z][a-z0-9-]*`.

Command specs are maps with:

```yaml
commands:
  status:
    exec: bin/status
    args: []
```

Relative `exec` paths resolve first relative to the plugin directory, then
relative to the repository root. Command `args` must be a list of strings.

## Provider Plugins

Provider plugins must expose:

```text
resolve init plan up down start stop status ip ssh
```

Core dispatch:

```bash
./scripts/provider-dispatch --instance <name> --command status
```

Provider commands receive resolved instance JSON on stdin. Interactive `ssh`
commands receive the same JSON in `EVE_RESOLVED_JSON` because stdin/stdout are
reserved for the terminal session.

Provider commands should write machine-readable JSON to stdout where practical
and logs to stderr.

Supported metadata:

```yaml
supports:
  engines: [terraform] # terraform|qemu|metal
  kinds: [vm]          # vm|metal
```

The core uses this metadata during instance resolution. A provider plugin that
does not support the resolved engine or machine kind is rejected before command
dispatch.

## Package Plugins

Package plugins must expose:

```text
install status down
```

Core dispatch:

```bash
./scripts/package-dispatch --instance <name> --package docker --command status
```

Package commands receive resolved instance JSON on stdin and the following env:

- `EVE_INSTANCE_NAME`
- `EVE_PACKAGE_PLUGIN`
- `EVE_PACKAGE_PLUGIN_ROOT`

Supported metadata:

```yaml
supports:
  os_families: [ubuntu, windows]
conflicts_with: [other-package]
compatibility_enforced: true
compatibility:
  - platform: ubuntu
    desktop: XFCE
    session: X11
    status: supported
    notes: Uses an isolated XFCE session.
```

`compatibility` is optional. It feeds Eve's new-instance package help and the
remote desktop compatibility docs. Each row must include `platform`, `desktop`,
`session`, `status`, and `notes`; status must be one of `supported`, `wip`,
`unsupported`, or `legacy`.

Set `compatibility_enforced: true` when package availability should be filtered
by the matrix. Eve and `package-list` then require a `supported` row matching
the selected OS family, desktop, and session. Leave it unset for ordinary
packages whose compatibility rows are informational.

`conflicts_with` is optional package metadata for mutually exclusive choices.
It is used for desktop-mode packages such as XFCE, GNOME, KDE, and their
headless variants. `instance-resolve`, `package-list`, and Eve all consume the
same manifest field, so these selection rules stay in configuration instead of
being embedded as package-name blocks in the UI.

Package `status` commands should emit one JSON object with:

```json
{
  "kind": "package-status",
  "package": "docker",
  "command": "status",
  "instance": "dev-a",
  "os_family": "ubuntu",
  "status": "installed",
  "details": "optional text"
}
```

Valid status values are `installed`, `missing`, `unknown`, and `failed`.
`package-dispatch status` stores that value in local instance state.

Package `down` may be marked destructive:

```yaml
down:
  destructive: true
```

Destructive `down` and `reinstall` require `--yes`, `YES=1`, or
`EVE_CONFIRM_DESTRUCTIVE=1`.

## Built-In Compatibility Wrapper

Most built-ins use:

```yaml
commands:
  install: {exec: scripts/package-plugin, args: [docker, install]}
  status: {exec: scripts/package-plugin, args: [docker, status]}
  down: {exec: scripts/package-plugin, args: [docker, down]}
```

The wrapper looks for plugin-local hooks:

- `commands/<os_family>/install`
- `commands/<os_family>/status`
- `commands/<os_family>/down`
- `commands/common/<command>`

If no package-specific install hook exists, built-ins can still use manifest
install metadata to call existing provisioning steps.

## Install Metadata

Ubuntu package install metadata:

```yaml
install:
  ubuntu:
    steps: [base.sh, timezone.sh, docker.sh]
    package_markers: [docker]
```

Windows package install metadata:

```yaml
install:
  windows:
    steps: [provision/windows/rustdesk.ps1]
    state_files: [env.json]
    fallback: false
```

`state_files` currently only accepts `env.json`.

## External Plugin Sources

`.eve/plugin-sources.yaml` uses:

```yaml
sources:
  - id: my-plugins
    url: https://github.com/example/eve-plugins.git
    ref: v1.0.0
```

`ref` is required by default. Unpinned sources require
`EVE_ALLOW_UNPINNED_PLUGINS=1`.

External repositories should contain the same manifest shape as built-ins. A
provider repository can expose one or more directories with
`eve-plugin.yaml`; a package repository can do the same. Keep command
implementations inside the plugin directory when possible so relative `exec`
paths remain portable after `make plugins.sync`.

Recommended repository layout:

```text
my-eve-plugins/
  packages/
    my-package/
      eve-plugin.yaml
      commands/ubuntu/install
      commands/ubuntu/status
      commands/ubuntu/down
  providers/
    my-provider/
      eve-plugin.yaml
      bin/provider-command
```

Development loop:

```bash
EVE_PLUGIN_ROOTS=/path/to/my-eve-plugins/packages/my-package make plugins.validate
EVE_PLUGIN_ROOTS=/path/to/my-eve-plugins/packages/my-package \
  ./scripts/package-dispatch --instance dev-a --package my-package --command status --dry-run
```

Before running a new external plugin against a real instance, run:

```bash
make doctor
make instance.validate INSTANCE=<name>
```

## Examples

See:

- `examples/plugins/packages/hello-package`
- `examples/plugins/providers/echo-provider`
