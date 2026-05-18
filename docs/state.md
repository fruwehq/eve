# v3 Instance State

Concrete instance state lives in `.egame/state/instances/<instance>.json` and
is updated through `scripts/instance-state`. Core dispatchers should not write
these JSON files directly.

## Top-Level States

- `desired_state`: `unknown`, `running`, `stopped`, `absent`
- `provider_state`: `unknown`, `initializing`, `initialized`, `planned`,
  `changing`, `running`, `stopped`, `absent`, `error`
- `provision_state`: `unknown`, `provisioning`, `provisioned`, `error`

## Package States

Package entries under `package_state` use:

- `unknown`
- `installed`
- `missing`
- `failed`
- `removed`
- `reinstalled`

Package state updates must pass both `--package` and `--package-state`.

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
make instance.observe INSTANCE=<name>
```

Observation refreshes set `EGAME_DISABLE_STATE=1` while calling provider
commands, so they do not append lifecycle operations to `operation_history`.

## Operation Entries

Every write records `last_operation` and appends to `operation_history`.
Operation entries include:

- `id`: monotonic per retained history window
- `name`: full operation name, such as `provider.up`, `package.status`, or
  `provision`
- `type`: operation prefix, such as `provider`, `package`, or `provision`
- `status`: `running`, `succeeded`, `failed`, or `skipped`
- `at`: UTC timestamp
- `error`: present only for failed or error-bearing entries

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
make instance.recover INSTANCE=<name>
```

This marks the last running operation as `failed`, records a recovery error, and
sets `provider_state` or `provision_state` to `error` when the interrupted
operation belongs to that surface. It does not destroy or change remote
resources. After recovery, run `make instance.status INSTANCE=<name>` and retry
the relevant lifecycle/provision/package command.
