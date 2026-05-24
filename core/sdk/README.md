# core/sdk — Provider Plugin SDK

The versioned public surface that provider and package plugins call.
Only files under `core/sdk/` are part of the plugin contract.

## Require entrypoint

```ruby
require_relative "../../core/sdk"
# or from a provider-command at plugins/providers/<id>/commands/:
require_relative "../../../../core/sdk"
```

All SDK modules are loaded by the entrypoint `core/sdk.rb`.

## Modules

### Eve::SDK::Resolve

Parse `EVE_RESOLVED_JSON` (from env or stdin) into a typed
`Eve::SDK::ResolvedInstance` struct. Validates against
`core/schema/resolved-instance.schema.json`. Raises
`Eve::SDK::SchemaValidationError` with a human-readable message on
invalid input.

### Eve::SDK::Workdir

Per-instance path helpers for state, Terraform data/state, logs,
uploads, config, registries, and plugin data. Honors `EVE_HOME`,
`EVE_STATE_DIR`, and `EVE_INSTANCE_WORKDIR` env overrides. `repo_root`
points at the source tree; `root` is the runtime data root and becomes
`EVE_HOME` when set. Produces the same paths as `scripts/instance-paths`.

### Eve::SDK::State

Read/write observed state and operation history. This is the seed for
the §C state-ownership migration. New SDK code should use these
helpers instead of calling `scripts/instance-state` directly.

### Eve::SDK::Log

Structured streaming output with line buffering and prefix support.
JSON output available via the `json:` keyword argument on `Log.emit`.

### Eve::SDK::Contract

Validate command input/output JSON against
`core/schema/command-io.schema.json`. Raises
`Eve::SDK::ContractError` on validation failure.

### Eve::Provider.dispatch(argv)

Replaces the 95-line provider-command wrapper. Parses the command,
loads and validates resolved instance JSON, derives provider id from
`EVE_PROVIDER_PLUGIN` or `$PROGRAM_NAME` path, handles dry-run/resolve
mode, and dispatches to `scripts/*` for implementation. Called as:

```ruby
Eve::Provider.dispatch(ARGV)
```

## Expected environment

The SDK expects to run inside the project repository with these
environment variables set by `scripts/provider-dispatch`:

- `EVE_RESOLVED_JSON` — full resolved instance JSON (or piped on stdin)
- `EVE_PROVIDER_PLUGIN` — the dispatching provider id
- `EVE_PLUGIN_DRY_RUN` — set to `"1"` for dry-run mode
- `EVE_HOME` — parent directory for `.eve/` and `.generated/` (optional)
- `EVE_STATE_DIR` — override state directory (optional)
- `EVE_INSTANCE_WORKDIR` — override workdir base (optional)

## Schema validation

The SDK validates at every boundary. Schema validation failure exits
with a clear error message, not a stack trace.

## Stability

Only `core/sdk/` is the plugin contract. Root `scripts/` are internal
implementation details and are **not** public plugin API. Plugins must
call SDK helpers, not shell into scripts directly. The SDK dispatches
to scripts internally, but that indirection will be removed when
scripts move into plugins in Part 2.
