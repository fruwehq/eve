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

### Egame::SDK::Resolve

Parse `EGAME_RESOLVED_JSON` (from env or stdin) into a typed
`Egame::SDK::ResolvedInstance` struct. Validates against
`core/schema/resolved-instance.schema.json`. Raises
`Egame::SDK::SchemaValidationError` with a human-readable message on
invalid input.

### Egame::SDK::Workdir

Per-instance path helpers for state, Terraform data/state, logs, and
uploads. Honors `EGAME_STATE_DIR` and `EGAME_INSTANCE_WORKDIR` env
overrides. Infers project root from its own filesystem location
(`core/sdk/` → two levels up). Produces the same paths as
`scripts/instance-paths`.

### Egame::SDK::State

Read/write observed state and operation history. This is the seed for
the §C state-ownership migration. New SDK code should use these
helpers instead of calling `scripts/instance-state` directly.

### Egame::SDK::Log

Structured streaming output with line buffering and prefix support.
JSON output available via the `json:` keyword argument on `Log.emit`.

### Egame::SDK::Contract

Validate command input/output JSON against
`core/schema/command-io.schema.json`. Raises
`Egame::SDK::ContractError` on validation failure.

### Egame::Provider.dispatch(argv)

Replaces the 95-line provider-command wrapper. Parses the command,
loads and validates resolved instance JSON, derives provider id from
`EGAME_PROVIDER_PLUGIN` or `$PROGRAM_NAME` path, handles dry-run/resolve
mode, and dispatches to `scripts/*` for implementation. Called as:

```ruby
Egame::Provider.dispatch(ARGV)
```

## Expected environment

The SDK expects to run inside the project repository with these
environment variables set by `scripts/provider-dispatch`:

- `EGAME_RESOLVED_JSON` — full resolved instance JSON (or piped on stdin)
- `EGAME_PROVIDER_PLUGIN` — the dispatching provider id
- `EGAME_PLUGIN_DRY_RUN` — set to `"1"` for dry-run mode
- `EGAME_STATE_DIR` — override state directory (optional)
- `EGAME_INSTANCE_WORKDIR` — override workdir base (optional)

## Schema validation

The SDK validates at every boundary. Schema validation failure exits
with a clear error message, not a stack trace.

## Stability

Only `core/sdk/` is the plugin contract. Root `scripts/` are internal
implementation details and are **not** public plugin API. Plugins must
call SDK helpers, not shell into scripts directly. The SDK dispatches
to scripts internally, but that indirection will be removed when
scripts move into plugins in Part 2.
