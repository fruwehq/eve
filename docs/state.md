# v4.5 Instance State

Concrete instance state lives in `.eve/state/instances/<instance>.json` and
is updated through `scripts/instance-state`. Core dispatchers should not write
these JSON files directly.

## Top-Level States

- `desired_state`: `unknown`, `running`, `stopped`, `absent`
- `provider_state`: `unknown`, `creating`, `starting`, `stopping`, `destroying`,
  `running`, `stopped`, `absent`, `error`
- `provision_state`: `unknown`, `provisioning`, `provisioned`, `error`

## Package States

Package entries under `package_state` use:

- `failed`
- `installed`
- `installing`
- `missing`
- `removed`
- `removing`
- `unknown`

Dispatchers derive package state by firing operation and observation events into
`core/fsm/package.yaml`. The `--package-state` pair remains available only for explicit
compatibility writes.

## Observed State Cache

`observed_state` stores the latest best-effort facts read from the provider or
guest without changing lifecycle intent:

- `provider_status`: normalized live status such as `running`, `stopped`,
  `absent`, `unreachable`, or `unknown`
- `provider_status_raw`: short provider status output
- `ip`: last known instance IP address
- `control_reachable`: whether the provider control path was reachable
- `control_summary`: provider control-path summary text
- `observed_at` / `expires_at`: cache timestamps
- `refresh_error`: last observation error, separate from lifecycle errors

Refresh it with:

```bash
eve instance observe --instance <name>
```

Observation refreshes set `EVE_DISABLE_STATE=1` while calling provider
commands, so they do not append lifecycle operations to `operation_history`.

## Operation Entries

Every write records `last_operation` and appends to `operation_history`.
Operation entries include:

- `id`: monotonic even after the retained history window is trimmed
- `name`: full operation name, such as `provider.up`, `package.status`, or
  `provision`
- `type`: operation prefix, such as `provider`, `package`, or `provision`
- `status`: `running`, `succeeded`, `failed`, or `skipped`
- `at`: UTC timestamp
- `error`: present only for failed or error-bearing entries
- `package`: package id, present on package operations

The history keeps the latest 50 entries by default.

## Current Transition Ownership

- `scripts/provider-dispatch` owns provider lifecycle state transitions.
- `scripts/package-dispatch` owns package status/install/down/reinstall state.
- `scripts/instance-provision` owns `provision_state`.
- Future reconcile commands should call these dispatchers instead of mutating
  state directly.

## Interrupted Operation Recovery

If the host process or TUI exits while an operation is marked `running`, recover
the local state before retrying:

```bash
eve instance recover --instance <name>
```

This marks the last running operation as `failed`, records a recovery error, and fires
the matching failure event into the provider, provision, or package machine. It does not
destroy or change remote resources. After recovery, run
`eve instance status --instance <name>` and retry the relevant command.
