# v3 Plugin Contracts

v3 keeps provider and package implementation details out of the core
orchestrator. Core scripts discover plugin manifests, validate their shape, and
dispatch commands with resolved instance JSON on stdin.

## Discovery

Built-in plugins live under:

- `plugins/providers/<id>/egame-plugin.yaml`
- `plugins/packages/<id>/egame-plugin.yaml`

External plugins may be synchronized into `.egame/plugins/<source-id>/` with:

```bash
make plugins.sync
```

Additional local roots can be tested without syncing:

```bash
EGAME_PLUGIN_ROOTS=examples/plugins/packages/hello-package make plugins.validate
```

If two plugins use the same `kind:id`, validation fails unless
`EGAME_PLUGIN_ALLOW_OVERRIDE=1` is set.

## Manifest Fields

Every manifest uses:

```yaml
api_version: egame.plugin/v1
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
commands receive the same JSON in `EGAME_RESOLVED_JSON` because stdin/stdout are
reserved for the terminal session.

Provider commands should write machine-readable JSON to stdout where practical
and logs to stderr.

Supported metadata:

```yaml
supports:
  engines: [terraform] # terraform|vagrant|metal
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

- `EGAME_INSTANCE_NAME`
- `EGAME_PACKAGE_PLUGIN`
- `EGAME_PACKAGE_PLUGIN_ROOT`

Supported metadata:

```yaml
supports:
  os_families: [ubuntu, windows]
```

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
`EGAME_CONFIRM_DESTRUCTIVE=1`.

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
    steps: [00_base.sh, 05_timezone.sh, 10_docker.sh]
    package_markers: [docker]
```

Windows package install metadata:

```yaml
install:
  windows:
    steps: [40_rustdesk.ps1]
    state_files: [env.json]
    fallback: false
```

`state_files` currently only accepts `env.json`.

## External Plugin Sources

`.egame/plugin-sources.yaml` uses:

```yaml
sources:
  - id: my-plugins
    url: https://github.com/example/egame-plugins.git
    ref: v1.0.0
```

`ref` is required by default. Unpinned sources require
`EGAME_ALLOW_UNPINNED_PLUGINS=1`.

## Examples

See:

- `examples/plugins/packages/hello-package`
- `examples/plugins/providers/echo-provider`
