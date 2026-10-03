# v4.5 recovery validation in Cloud

Validated on 2026-10-04 from fresh GitHub recovery checkouts. No backup files or
ignored personal configuration were used. All five initial heads matched the
recovery request:

| Repository | Recovery PR | Initial head |
| --- | --- | --- |
| eve | #56 | c2c0f5a |
| eve-providers | #11 | 16ef4ef |
| eve-packages-linux | #7 | 5f9bb7c |
| eve-packages-windows | #5 | 5b4e261 |
| eve-plugins-ai | #3 | 1557a55 |

## Determa API and version

The [Python upstream release](https://github.com/fruwehq/determa-state-python/releases/tag/v0.2.0),
[specification release](https://github.com/fruwehq/determa-state-spec/releases/tag/v0.2.0),
and PyPI release metadata all identify 0.2.0 as the latest release. No newer
compatible or breaking release was found. Retain `>=0.2.0,<0.3.0` and the existing
0.2.0 lockfile entry.

Eve uses the documented public `load_bundle`, `create`, and `dispatch` functions,
format-1 machine definitions, root-targeted event envelopes, external bindings,
and reserved `env` refresh events. Aggregate `runtimes`, active paths, and root
scopes are documented public state data. Side effects remain host-owned.
`ExecutionHost` is optional; its checkpoint stores are not required for pure
foreground transitions. Eve's small seed-by-replay adapter is restricted to its
context-free finite lifecycle graphs. A future machine with context or history
must persist and restore the complete aggregate, as the adapter documents.
No Determa design defect requiring an upstream issue was reproduced.

## Fresh validation

The Cloud environment used Python 3.12.14, dependencies installed from
`poetry.lock`, Terraform 1.14.9, Terramate 0.17.0, ShellCheck 0.11.0, and portable
PowerShell 7.5.4. PowerShell's writable XDG directories were isolated for testing.

- The full `scripts/test` passed. Final validation of all Python tests passed
  528 tests with one intentional skip (an empty-registry instance comparison).
- The standalone FSM tests now run with the default Python suite, rather than
  being omitted by its old `tests/python` selection.
- Linux launcher tests: 23 passed with `python -m pytest -q tests`.
- Providers: all seven provider conformance checks, host-resolver checks, five
  AWS connectivity tests, five status-error tests, and environment contracts passed.
- Every tracked manifest across all four companion repositories passed
  conformance, including nested bundle and OS manifests.
- The combined catalog loaded 47 plugins: seven providers, 25 packages, eleven
  bundles, and four OS plugins. Shared Linux/Windows package configuration
  schemas match; standalone bundle membership resolves.
- Actual OS runners passed failure, success, resume, manifest, and structured
  status checks. PowerShell additionally passed explicit exit, thrown-error,
  and informational native-tool exit cases.
- ShellCheck and Ruff passed for provider and Linux scripts. All 22 tracked
  provider/Windows PowerShell files parsed successfully.
- External provider stack staging, Terramate generation, Terraform formatting,
  Terramate formatting, and the core boundary check with real plugins passed.
- Linux and Windows integration plans, including all applicable packages, were
  generated from synthetic instances. Fake-provider lifecycle tests exercised
  create/status/IP/stop/start/provision/destroy without live infrastructure.

Reproduce cross-repository checks from the core checkout:

```sh
scripts/test-cross-repo \
  --plugin-root ../eve-providers \
  --plugin-root ../eve-packages-linux \
  --plugin-root ../eve-packages-windows \
  --plugin-root ../eve-plugins-ai
scripts/test-provision-runner --plugin-roots ../eve-providers
```

Run with the core project environment on `PATH`. Add `pwsh` to `PATH` for Windows
runner checks. The ordinary core suite stays hermetic; cross-repository runners
accept explicit roots and never need live providers.

## Audit findings and fixes

Determa remains the transition authority for provider, provisioning, package,
and interrupted-operation recovery. Operation IDs are allocated under the state
lock and remain monotonic when history is trimmed. Authentication evaluates all
universal requirements plus at least one complete alternative group
(`required_any` is OR-of-AND). Provider and package command environments are
operation-local and inject only declared target credentials.

Fresh checks identified and fixed these additional problems:

- Nested package observations could supply a root status through line scanning.
  JSON extraction now skips nested objects and reads the last matching root.
- Secret payload files are created with mode 0600 before bytes are written,
  including Windows JSON. Remote state directories are restricted before upload.
  Partial secret uploads trigger cleanup. Failed Windows deletions and native
  ACL errors propagate instead of silently succeeding.
- Literal shell quoting had prevented staged installer paths from expanding
  `$HOME`. Only that known prefix expands; filenames and secrets stay quoted.
- The Windows runner treated an explicit `exit 42` as success. Each step now
  executes in the current PowerShell runtime's separate `-File` process.
- Terraform status helpers suppressed backend failures. Missing explicit local
  state remains absence; generation, backend, malformed JSON, and AWS API
  failures now propagate. No alternate backend is queried for missing explicit
  instance state.
- Linux contained tracked bytecode and lint findings. Bytecode was removed,
  generated Python artifacts ignored, and lint findings fixed.
- Core contained a concrete provider identifier in an FSM comment that failed
  the real-plugin core boundary check. The example is now generic.

## GitHub and remaining rollout dependency

Core recovery CI skipped because its PR was a draft; the cross-repository job is
scheduled/manual only. Provider and Linux/Windows recovery CI was absent because
those workflows filtered PR bases to `main`. Companion workflows now include
`v4.5`, select the corresponding core ref, and validate nested manifests. Core
and companion workflows explicitly handle `ready_for_review`. Provider CI now
runs status-error and OS-runner tests, and Linux CI runs its launcher suite.

Enabling core CI exposed a pre-existing environment mismatch: Poetry created a
cached environment while the test runners require `.venv/bin/python`. The
workflow now explicitly creates its environment inside the project, as used in
fresh Cloud validation, and the pipeline contract check enforces this setting.

No open issues or unresolved review threads were found on the affected PRs.
The only additional open PR found was Eve #46, a TUI portrait-blink change
outside this migration. Its `tui/app.py` overlap should be reviewed separately;
its code was not incorporated into recovery.

Offline readiness does not establish live Windows GPU usability. The existing
v4.5 roadmap still requires a Vultr `vultr-vcg-a40-2c` Windows gaming instance
with the VDD as the sole active display and working Sunshine streaming. Cloud
currently has no provider secret or outbound identity bindings. Main-facing PRs
must state this remaining live dependency accurately; do not claim that demo or
GPU validation has occurred. No billable resources were created.
