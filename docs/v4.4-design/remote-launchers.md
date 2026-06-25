# v4.4 §8 — Package-owned remote launchers (design)

Status: **contract settled (review decisions folded in).** This is the last
v4.4 item that lets core know *what packages do*; finishing it unblocks the §11
package-id lint ban.

## Problem — three distinct leaks

Core currently knows package specifics in three places:

1. **Launcher argv construction** — `eve_sdk/remote_launch.py` builds the
   `moonlight`, `sunshine`, `rustdesk`, `thinlinc`, `vnc`, `waypipe`, `xpra`
   client command vectors (platform branches, env-conditional flags, enum
   validation). `scripts/remote-*` are the core launcher entry points.
2. **Vagrant port-forwards** — `eve_sdk/profile_resolve.py:367–393` branches on
   `sunshine`/`vnc`/`xpra`/`rdp`/`thinlinc` to emit per-package forwarded ports
   into the Vagrantfile.
3. **Bundle-compatibility guard** — `eve_sdk/dispatch.py:275` special-cases
   `rustdesk` + `gnome-desktop` on ubuntu — core hardcoding a rule about how two
   *named* packages interact.

Non-trivial cases the contract must cover (called out up front):
- **moonlight's validated env knobs** — `EPHEMERAL_MOONLIGHT_DISPLAY_MODE` /
  `VIDEO_CODEC` / `VIDEO_DECODER` are enum-validated today (exit 2 on bad value).
- **the sunshine↔moonlight pairing handshake** — multi-step: POST a PIN to the
  Sunshine API via `curl` (`sunshine_pair_curl_command`), check the response,
  then `Moonlight pair --pin <pin> <ip>` (`moonlight_pair_command`).
- **platform-specific executables** — macOS `.app` bundles vs Linux/Windows
  binaries (e.g. `rustdesk_local_client`'s candidate walk).

## Design — reuse what the manifest already has

Two earlier proposals (`remote_client.exec`, `incompatible_with_bundles`) were
**rejected on review** because they reinvent manifest concepts that already
exist. The corrected design adds almost no new surface.

### A launcher is just an action (no new `remote_client` field)

A package already contributes **actions** to an instance — sunshine's manifest
declares them today:

```yaml
actions:
  - { id: sunshine,       label: Sunshine,      target: sunshine.open }
  - { id: pair-moonlight, label: Pair Moonlight, target: moonlight.pair }
  - { id: moonlight,      label: Moonlight,     target: moonlight.open }
```

So "launch the remote client" is **not a special concept** — it is one of the
actions a package already exposes, each backed by a package command. There is
no `remote_client` block: a launcher action's `target` resolves to a package
command (`exec`), exactly like provider commands. This also answers the old
"single launcher vs. map" question — it's neither; it's the existing per-action
`target → command` mapping, so sunshine's three surfaces are just three
actions. `pair` and `open` are distinct actions, not subcommands of one script.

### Compatibility is capability-based, never package-named

Rejected: `incompatible_with_bundles` listing other packages. A package **cannot
enumerate an open, unknown set of future packages** — naming `gnome-desktop` is
the same class of leak as core naming `rustdesk`, just relocated. Instead, use
the **capabilities / requires** model the schema already has (`capabilities`,
`compatibility`, `requires` all exist):

- A package/bundle **provides** abstract capability tokens
  (e.g. a desktop bundle provides `session:wayland` or `session:x11`).
- A package **requires** / **conflicts-with** capability tokens, never package
  ids (e.g. rustdesk requires `capture:unattended`, which a Wayland session does
  not provide; or rustdesk conflicts with `session:wayland`).

The resolver detects the rustdesk+GNOME clash because GNOME's session provides
`session:wayland` and rustdesk requires an X11/unattended-capture capability —
**no package names either side.** Any future package slots into the same
negotiation by declaring the capabilities it provides/needs. Core just matches
tokens; it learns nothing about specific packages.

### Vagrant port-forwards stay declarative (this one is fine)

A package declaring the guest/host ports it needs forwarded is **self-contained**
— it names only its own ports, not other packages — so it is a legitimate
manifest field, not a leak:

```yaml
vagrant:
  port_forwards:
    - { guest: 47984, host: 47984 }
    - { guest: 47998, host: 47998, protocol: udp }
```

Core aggregates `port_forwards` across the resolved bundle's packages instead of
branching on package ids in `profile_resolve.py`.

## Core's generic dispatch contract

Core keeps the **shared spine** (identical for every client) and execs the
package's action command:

1. Resolve the shared context once — profile env via `profile-resolve`, IP via
   `instance-ip`, unix user, SSH key, bundle membership. Kept generic in
   `eve_sdk`; no package id appears.
2. Export the context as env. `EVE_REMOTE_*` (`EVE_REMOTE_IP`, `EVE_REMOTE_USER`,
   `EVE_REMOTE_KEY`, `EVE_REMOTE_OS_FAMILY`, `EVE_REMOTE_ENGINE`,
   `EVE_REMOTE_ACTION`) is the **documented stable contract**; the full resolved
   `profile-resolve` env + `BUNDLE_PACKAGES` are also exported as passthrough so
   launchers that read many vars today keep working. (Packages get their *own*
   config as env via the §2/§3 manifest mechanism — see "Configuration" below.)
3. Resolve the selected action's `target` to its package command and `exec` it
   with that env. **No package id appears in core dispatch.**

### Launcher selection

Selection is **explicit** — the action carries its package. The TUI already
lists per-package actions; the CLI surface is `eve remote <package> <action>`
(or the action id, which maps to one package). If the named package/action is
not in the resolved bundle, fail with a clear message — **no fallback, no
guessing.** This preserves "no package id in core dispatch" while keeping the
command unambiguous when a bundle has several remote-capable packages.

### Configuration (Q4 resolved)

A plugin (package *or* provider) declares its own config fields in its manifest
`config_schema` and reads them as env vars — already built in §2/§3 (the
`_plugin_mappings` scan covers packages). The `moonlight` config rows leave
`config.py` and become `config_schema` fields on the **sunshine** manifest
(moonlight is sunshine's client; sunshine already owns the moonlight actions).
Core additionally exposes a small fixed set of **global convenience vars**
(e.g. default account/user name) that any plugin may read — these are the only
config names core itself owns.

### How the non-trivial cases map

| Case | Today (core) | After (package) |
|---|---|---|
| moonlight enum knobs | `_MOONLIGHT_*` sets + exit-2 guards in `remote_launch.py` | sunshine's launcher command validates its own env, exits non-zero on bad value |
| sunshine↔moonlight pair | `sunshine_pair_curl_command` + `moonlight_pair_command` in core | sunshine's `moonlight.pair` action command runs both steps (it owns the handshake) |
| platform executables | `rustdesk_local_client` candidate walk in core | each package's launcher does its own `command -v` / `.app` walk |
| rustdesk + GNOME clash | `dispatch.py:275` names both packages | capability tokens: GNOME provides `session:wayland`, rustdesk requires unattended/X11 capture |

## Migration plan

1. **Schema:** add `vagrant.port_forwards` to the manifest schema and define the
   capability-token vocabulary for provides/requires/conflicts (reusing existing
   `capabilities`/`requires`/`compatibility`). No `remote_client` field — reuse
   `actions` + `target → command`.
2. **Core dispatcher:** generic remote-action path (shared spine reused) that
   resolves an action's target to a package command and execs it with
   `EVE_REMOTE_*` + profile env. Aggregate `port_forwards` across the bundle.
   Replace the `dispatch.py` rustdesk branch with capability matching.
3. **Per package** (`eve-packages-linux`/`-windows`, release-coupled): add the
   launcher command behind each existing action target, the package's
   `port_forwards`, and its capability provides/requires. Move the `moonlight`
   config rows + launcher onto the sunshine manifest.
4. **Delete** `eve_sdk/remote_launch.py` client builders + `scripts/remote-*` +
   the `profile_resolve.py` port-forward branches.
5. **Flip on the §11 package-id ban** in `scripts/test-core-boundary`
   (`load_all("package")` in the banned set, `COMMON_TOKEN_IDS` for dual-meaning
   names) — **last**, once the leaks are gone.
6. **Cross-repo parity check:** point eve at the package PR branches via
   `EVE_PLUGIN_ROOTS` and confirm each remote client still launches and the
   capability clash is still detected. Core + the package PRs merge together
   (core-first breaks the launchers).

## Resolved review decisions

1. **Launcher model** — reuse `actions` + per-action `target → command`; no
   `remote_client` field, no subcommand DSL.
2. **moonlight home** — directly on the sunshine manifest (config rows + launcher
   command); it is sunshine's client, not a standalone package.
3. **Compatibility** — capability tokens (provides/requires/conflicts), never
   package names; `incompatible_with_bundles` rejected.
4. **Config** — plugin-owned `config_schema` env vars (per §2/§3) + a small fixed
   set of core global convenience vars. Full profile-resolve env exported as
   passthrough; `EVE_REMOTE_*` is the documented stable contract.
5. **Launcher selection** — explicit `eve remote <package> <action>` / action id;
   fail clearly if not in the resolved bundle (no fallback).
