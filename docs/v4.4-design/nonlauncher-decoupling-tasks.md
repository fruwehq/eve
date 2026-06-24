# v4.4 §15 — decouple the non-launcher package-id subsystems (task spec)

Roadmap item: `docs/v4.4-roadmap.md` §15. Surfaced by §8: the §11 **package-id**
ban can't flip green because four subsystems beyond the launcher surface still
name packages. Each is its own decoupling toward manifest/capability-driven
behavior so core names no package. Smaller than §8/§14 but real.

**Run end-to-end autonomously** (same rules as the §8/§14 specs): phases are
commit/bisect boundaries, not approval gates; self-verify each against the health
gate; branch **`v4.4`** only; run pytest with `.venv/bin` on `PATH`. The §6 ban
flip is shared with §8 Phase 6 — do it once, last, after both §8 and §15 are clean.

## Health gate (every phase)

```
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q
.venv/bin/python -m ruff check eve_sdk tui scripts
.venv/bin/python -m mypy eve_sdk
scripts/test-core-boundary
```

---

## Phase 1 — provision env model  *(eve core; release-coupled with packages)*

`scripts/provision` hardcodes package env vars into the env.json export
(`provision:269–276`: `EPHEMERAL_SUNSHINE_PASSWORD`, `RUSTDESK_KEY/PASSWORD`,
`NOMACHINE_VERSION`, `SPLASHTOP_*`). **Do:** emit package env from the installed
package manifests' `config_schema` — the same `_plugin_mappings` source §2/§3
established for config-env — so provision aggregates package env generically
instead of naming packages. Confirm via cross-repo parity that the same env keys
still reach the remote for each package. Commit:
`refactor(provision): package env from manifests, not hardcoded keys (§15)`.

## Phase 2 — update-tools  *(eve core + packages)*

`scripts/update-tools:68` hardcodes rustdesk/sunshine apt upgrades. **Do:** each
package declares its update/upgrade step (a manifest field or an action target);
`update-tools` aggregates the steps across installed packages and runs them
generically. Commit: `refactor(update-tools): package-declared upgrade steps (§15)`.

## Phase 3 — package-verify  *(eve core + packages)*

`scripts/package-verify:161` hardcodes `verify_rdp` and similar per-package
checks. **Do:** each package declares its own verify hook (manifest field /
command); core runs them generically. Commit:
`refactor(package-verify): package-declared verify hooks (§15)`.

## Phase 4 — desktop detection by capability  *(eve core + packages)*

`eve_sdk/instance_view.py:69–75` and `tui/widgets.py` `DESKTOP_PACKAGE_IDS`
branch on `gnome-desktop`/`kde-desktop`/`xfce-desktop` ids. **Do:** desktop
packages declare a capability (e.g. `provides: [desktop]`, plus the specific
desktop name as data if the UI needs it); core/TUI detect "has a desktop" and
which one via the capability/data, not an id list. Commit:
`refactor(desktop): capability-driven desktop detection (§15)`.

## Phase 5 — cross-repo parity

```
EVE_PLUGIN_ROOTS_EXCLUSIVE=1 EVE_PLUGIN_ROOTS="<eve-packages-linux>:<...>" \
  PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/python -q
```

Confirm provision env, tool updates, verify, and desktop detection still behave
for every affected package with the real manifests present. No fallback paths.

## Phase 6 — flip the §11 package-id ban  *(shared with §8 Phase 6; do once, LAST)*

Only after §8 (launchers, done) **and** §15 Phases 1–5 leave core package-id
free: add `load_all("package")` ids to `scripts/test-core-boundary`'s banned set
(reuse `COMMON_TOKEN_IDS` for dual-meaning names like `docker`/`vnc`). Run green;
fix any straggler. Update `docs/v4.4-roadmap.md` §8/§11/§15 — package-id ban done.

Commit: `chore(lint): ban package ids in core-boundary; v4.4 §8/§15 done`.

## Merge discipline

eve `v4.4` + `eve-packages-linux` (manifest additions for env/update/verify/
desktop) merge together — core-first breaks these subsystems. Run Phase 5 parity
green before any merge.
