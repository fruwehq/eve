# v3.1 Part 3 finish report

Branch: v3.1
Head before: 40e0750
Files staged: 16

## Task 1 — Desktop status commands
Status: done
Packages updated: xfce-desktop, xfce-desktop-headless, gnome-desktop-headless, kde-desktop, kde-desktop-headless
Probes used:
- xfce-desktop / xfce-desktop-headless: `dpkg -s xfce4`
- gnome-desktop-headless: `dpkg -s gnome-session`
- kde-desktop / kde-desktop-headless: `dpkg -s kde-plasma-desktop`
Each package now has both `commands/ubuntu/status` and `commands/ubuntu/down`.
Tests run: make test.plugins

## Task 2 — TUI provider pane
Status: done
Manual UI check: not performed (no live TUI in this session; compile-check and type-check pass)
Implementation:
- `tui/commands.py`: added `provider_pane_data()` (loads provider actions, filters out debug-only actions status/plan/init), `provider_dispatch_provider_args()`
- `tui/widgets.py`: added `ProviderPane` widget with per-provider rows showing name, reachable indicator, and action buttons. Emits `ActionRequested` messages on click.
- `tui/app.py`: wired ProviderPane into left panel compose, loads provider data on startup, handles interactive (login/host-ssh) and non-interactive dispatch via `scripts/provider-dispatch --provider <id> --command <action>`.
Tests run: make test.tui, make test.python

## Task 3 — Discord compatibility note
Status: done
Added `compatibility_enforced: false` and `compatibility:` block with ubuntu (supported) and windows (supported with audio caveat notes) entries.
Note: `status: optional` was not valid per the JSON schema; used `status: supported` with notes explaining the streaming protocol audio caveat.
Tests run: make test.schemas

## Task 4 — Roadmap doc tense
Status: done
- `docs/v3.1-roadmap.md`: re-tensed Part 1 (Architecture A–H) and Part 2 (Tactical §1–§6) from imperative/future to past tense. 90 lines changed.
- `docs/v3.1-provider-plugin-boundaries-plan.md`: re-tensed summary section (6 lines). Part 3 and Beyond v3.1 sections left untouched as forward-looking.

## Test suite
make test: all green (15 suites, 2 skipped for missing bash>=4/pwsh on host)

## Open follow-ups (not blocking merge)
- Manual TUI smoke: launch `make eve`, verify provider rows appear with Login/SSH buttons, test click dispatch
- The ProviderPane currently filters out debug actions (status/plan/init) from provider rows; could be expanded to include them if desired
- v3.2 §1 (schema-driven config) is ready to begin per the optional scope
