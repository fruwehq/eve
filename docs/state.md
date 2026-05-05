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

The history keeps the latest 50 entries by default. Set
`EGAME_STATE_HISTORY_LIMIT` to tune this locally; values are clamped between 1
and 500.

## Current Transition Ownership

- `scripts/provider-dispatch` owns provider lifecycle state transitions.
- `scripts/package-dispatch` owns package status/install/down/reinstall state.
- `scripts/instance-provision` owns `provision_state`.
- Future reconcile commands should call these dispatchers instead of mutating
  state directly.
