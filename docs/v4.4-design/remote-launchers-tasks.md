# v4.4 §8 — implementation task spec (for the coop coding agent)

Read `docs/v4.4-design/remote-launchers.md` first — that is the settled contract.
This file is the execution plan: **one phase per commit**, each self-contained for
a cold session. Work on branch **`v4.4`** only — no separate/stacked PRs (see
`docs/v4.4-roadmap.md` and the single-PR rule). Spans three repos; **core and the
package repos must merge together** (core-first drops launchers/env — verified
parity landmine). Run pytest with `.venv/bin` on `PATH` or the subprocess command
tests spuriously fail on Python 3.9.

## Goal

Core stops knowing *what packages do*. After §8, no package id appears in:
- `scripts/package-action` (`run_action_target`'s hardcoded target→`remote-*` map)
- `eve_sdk/remote_launch.py` (541 lines of per-client argv builders)
- `scripts/remote-*` (the per-client launcher entry points)
- `eve_sdk/profile_resolve.py:367–393` (per-package Vagrant port-forwards)
- `eve_sdk/dispatch.py:275` (the rustdesk+GNOME guard)

The launcher is an **existing action** (`target → package command`); compatibility
is **capability-based** (provides/requires tokens), never package-named.

## Health gate (run every phase before committing)

```
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q   # full suite green
.venv/bin/python -m ruff check eve_sdk tui scripts
.venv/bin/python -m mypy eve_sdk            # strict, as configured
scripts/test-core-boundary                  # provider/OS-id ban (package ban flips in Phase 6)
```

---

## Phase 1 — manifest schema: `port_forwards` + capability vocabulary  *(eve core)*

`core/schema/plugin-manifest.schema.json` already has `actions`, `capabilities`,
`requires`, `compatibility`. Add only what's missing:

1. **`vagrant.port_forwards`** — optional array of `{guest:int, host:int, protocol?:enum[tcp,udp]}`.
   A package names only its own ports (self-contained, not a leak).
2. **Capability tokens** — define the provides/requires/conflicts vocabulary on
   top of the existing `capabilities`/`requires` so a package can require/conflict
   an *abstract token* (e.g. `capture:unattended`, `session:wayland`), never a
   package id. Decide token namespace shape (`<facet>:<value>`) and document it in
   the schema `description`.

Do NOT add a `remote_client` field — launchers reuse `actions` + `target`.
Health gate + commit: `feat(schema): port_forwards + capability tokens for §8`.

## Phase 2 — generic launcher dispatch in core  *(eve core, additive)*

Make `scripts/package-action:run_action_target` generic **without** deleting the
old map yet (keep the build green; packages aren't migrated until Phase 3):

1. In each package manifest's `actions[]`, support an optional `exec` (relative to
   the package dir) and optional `wait_for` (another action target to run first,
   replacing the hardcoded `wait_for_sunshine`). When an action declares `exec`,
   `run_action_target` resolves the package dir, exports the shared context, and
   execs it — **no target string is interpreted by core**.
2. **Shared context export** (keep the spine from `remote_launch.py`): resolve
   profile env (`profile-resolve`), IP (`instance-ip`), unix user, SSH key, bundle
   membership — then export `EVE_REMOTE_IP/USER/KEY/OS_FAMILY/ENGINE/ACTION` (the
   documented stable contract) **plus** the full resolved profile env +
   `BUNDLE_PACKAGES` as passthrough. Keep the existing `load_runtime_env` call.
3. Fallback during migration: if an action has no `exec`, use the existing
   hardcoded map. This keeps every client working mid-migration. (The map is
   deleted in Phase 4.)

Add a test asserting an `exec`-declared action is dispatched generically with the
`EVE_REMOTE_*` env set. Health gate + commit:
`feat(dispatch): generic action-exec launcher path (spine reused) §8`.

## Phase 3 — migrate launchers into packages  *(eve-packages-linux + -windows; release-coupled)*

For every package that owns a `remote-*` launcher (sunshine, rustdesk, nomachine,
splashtop, thinlinc, vnc, waypipe, xpra, rdp — map them from `scripts/package-action`
and `scripts/remote-*`):

1. Add `commands/<launcher>` to the package, porting the argv-builder logic from
   the matching `eve_sdk/remote_launch.py` function(s) and the `scripts/remote-*`
   entry point. Bash or Python — packages may use bash. Preserve behavior exactly,
   including: moonlight env-knob enum validation (exit non-zero on bad value), the
   sunshine↔moonlight pairing handshake (curl PIN → `moonlight pair`), and the
   platform candidate walks (`.app` vs PATH).
2. Wire each action's `exec` (+ `wait_for` where needed) in the manifest.
3. **moonlight is sunshine's client** — its launcher commands (`moonlight.open`,
   `moonlight.pair`) and its `config.py` config rows (`EPHEMERAL_MOONLIGHT_*`,
   bitrate/display knobs) move onto the **sunshine** manifest's `config_schema`
   (they then emit via the §2/§3 `_plugin_mappings` package scan).
4. Add each package's `vagrant.port_forwards` and capability `provides`/`requires`
   (e.g. rustdesk requires `capture:unattended`; the GNOME/wayland desktop bundle
   provides `session:wayland` and not unattended capture).

Health gate: in the package repos, plus cross-repo parity from eve (Phase 6 check
can be run early). Commit per repo: `feat(packages): own remote launchers + config (v4.4 §8)`.

## Phase 4 — delete the core leaks  *(eve core; merges with Phase 3)*

Now that packages own everything:

1. Delete `eve_sdk/remote_launch.py` client builders (keep only the generic spine
   helpers still used by the dispatcher; move them if cleaner) and delete
   `scripts/remote-*`. Delete the hardcoded `mapping`/branches in
   `run_action_target` — it is now purely generic.
2. Replace `profile_resolve.py:367–393` per-package port-forward branches with
   **aggregation of `vagrant.port_forwards`** across the resolved bundle's packages.
3. Replace `dispatch.py:275` rustdesk+GNOME branch with **capability matching**
   (reject when a required capability is unmet / a conflict token is present). No
   package id on either side.
4. Remove the moonlight rows from `eve_sdk/config.py` `MAPPINGS` (now on sunshine).

Delete the now-dead `remote_launch` parity tests; add tests for port-forward
aggregation and capability-conflict rejection. Health gate + commit:
`refactor(core): drop per-package launchers/branches; capability+port aggregation §8`.

## Phase 5 — cross-repo parity verification

Point eve at the package PR branches and confirm nothing regressed:

```
EVE_PLUGIN_ROOTS_EXCLUSIVE=1 EVE_PLUGIN_ROOTS="<pkg-linux>:<pkg-windows>" \
  PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q
```

Manually confirm: each action still launches its client; moonlight env-validation
still exits non-zero on bad values; the sunshine pairing handshake still works; the
rustdesk+GNOME clash is still detected (now via capability tokens). No fallback
paths anywhere — a missing launcher/capability must fail loudly.

## Phase 6 — flip the §11 package-id ban  *(eve core; LAST)*

Only after Phases 1–5 leave core package-id free:

1. In `scripts/test-core-boundary`, add `load_all("package")` ids to the banned
   set (today only `provider_ids()` are banned). Reuse the existing
   `COMMON_TOKEN_IDS` context matching for dual-meaning names (e.g. `docker`,
   `vnc`). Keep the widened scan scope (`scripts/`, `eve_sdk/`, `tui/`, `config/`,
   `core/schema/`).
2. Run it — it must be green (fails if any package id remains). Fix any straggler.
3. Update `docs/v4.4-roadmap.md`: mark §8 and §11 **done**; update the status
   block and sequencing. v4.4 is then complete.

Health gate + commit: `chore(lint): ban package ids in core-boundary; v4.4 §8/§11 done`.

## Merge discipline

eve `v4.4` (PR #50) + eve-packages-linux #4 (or its §8 successor) + eve-packages-windows
+ eve-providers #7 merge **as one coupled set**. Core-first breaks launchers and
drops env. Run Phase 5 parity green before any merge.
