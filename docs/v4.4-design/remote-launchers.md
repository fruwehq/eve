# v4.4 §8 — Package-owned remote launchers (design, pre-review)

Status: **design proposal — awaiting review.** Do not migrate scripts until the
contract below is settled. This is the last v4.4 item that lets core know *what
packages do*; finishing it unblocks the §11 package-id lint ban.

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
   `rustdesk` + `gnome-desktop` on ubuntu (a bundle-composition rule the
   manifest `compatibility` matrix does not express).

Non-trivial cases the contract must cover (called out up front):
- **moonlight's validated env knobs** — `EPHEMERAL_MOONLIGHT_DISPLAY_MODE` /
  `VIDEO_CODEC` / `VIDEO_DECODER` are enum-validated today (exit 2 on bad value).
- **the sunshine↔moonlight pairing handshake** — multi-step: POST a PIN to the
  Sunshine API via `curl` (`sunshine_pair_curl_command`), check the response,
  then `Moonlight pair --pin <pin> <ip>` (`moonlight_pair_command`).
- **platform-specific executables** — macOS `.app` bundles vs Linux/Windows
  binaries (e.g. `rustdesk_local_client`'s candidate walk).

## Design decision — package-declared launcher *commands*, not an argv DSL

A declarative argv template (flags/env/placeholders) was considered and
rejected: it cannot cleanly express multi-step handshakes, platform candidate
walks, or response parsing without becoming a bad scripting language. Instead,
mirror the **provider-command model**: each package ships a launcher command,
and core invokes it generically with a shared context.

This keeps all client knowledge in the package (where bash is allowed), and
core's "shared spine" — resolve profile env, locate IP, validate the unix user,
resolve the SSH key, check bundle membership — stays generic in core (it is
identical for every client).

### Proposed manifest additions

```yaml
# 1. Remote-client launcher. Core resolves the shared context and execs this.
remote_client:
  exec: commands/remote-launch          # package script (bash or python)
  env:                                  # documented/validated knobs this launcher reads
    - EPHEMERAL_MOONLIGHT_DISPLAY_MODE  #   (enum validation moves into the script)
    - EPHEMERAL_MOONLIGHT_VIDEO_CODEC
    - EPHEMERAL_MOONLIGHT_VIDEO_DECODER

# 2. Vagrant port-forwards this package contributes (replaces profile_resolve branches).
vagrant:
  port_forwards:
    - { guest: 47984, host: 47984 }
    - { guest: 47998, host: 47998, protocol: udp }

# 3. Bundle-level incompatibility rules (replaces the dispatch.py rustdesk branch).
#    Extends the existing per-platform `compatibility` matrix with bundle rules.
incompatible_with_bundles:
  - { desktop: GNOME, reason: "RustDesk cannot unattended-capture GNOME/Wayland sessions" }
```

### Core's generic dispatch contract

A new generic remote-action path replaces the per-client `scripts/remote-*`:

1. Resolve the shared context once (profile env via `profile-resolve`, IP via
   `instance-ip`, unix user + SSH key + bundle membership) — the existing spine
   in `remote_launch.py`, kept generic.
2. Export the context as env (`EVE_REMOTE_IP`, `EVE_REMOTE_USER`,
   `EVE_REMOTE_KEY`, `EVE_REMOTE_OS_FAMILY`, `EVE_REMOTE_ENGINE`, plus the full
   resolved profile env + `BUNDLE_PACKAGES`).
3. Look up the selected package's declared `remote_client.exec` and `exec` it
   with that env. **No package id appears in core dispatch.**

The package's `commands/remote-launch` reads `EVE_REMOTE_*` + the profile env,
builds its client argv (incl. platform branches, enum validation, the pairing
handshake), and `exec`s it. `moonlight` (sunshine's client) lives in the
**sunshine** package's launcher; `config.py`'s `moonlight` rows move onto the
sunshine manifest at the same time.

### How the non-trivial cases map

| Case | Today (core) | After (package) |
|---|---|---|
| moonlight enum knobs | `_MOONLIGHT_*` sets + exit-2 guards in `remote_launch.py` | sunshine's `commands/remote-launch` validates its own env, exits non-zero on bad value |
| sunshine↔moonlight pair | `sunshine_pair_curl_command` + `moonlight_pair_command` in core | sunshine's launcher runs both steps (it owns the handshake) |
| platform executables | `rustdesk_local_client` candidate walk in core | each package's launcher does its own `command -v` / `.app` walk |

## Migration plan (after this design is approved)

1. Add the three manifest fields to `core/schema/plugin-manifest.schema.json`
   and a generic `remote_client` dispatcher in `eve_sdk` (shared spine reused).
2. Per package in `eve-packages-linux`/`-windows`: add `commands/remote-launch`
   + `remote_client`/`vagrant.port_forwards`/`incompatible_with_bundles` to each
   manifest; move the `moonlight` config rows onto sunshine.
3. Delete `eve_sdk/remote_launch.py` client builders + `scripts/remote-*`;
   replace the `profile_resolve.py` port-forward branches and the
   `dispatch.py` rustdesk branch with manifest-driven aggregation.
4. Flip on the §11 package-id ban in `scripts/test-core-boundary`
   (`load_all("package")` in the banned set, `COMMON_TOKEN_IDS` for
   dual-meaning names) — **last**, once the leaks are gone.
5. Cross-repo parity check: point eve at the package PR branches via
   `EVE_PLUGIN_ROOTS` and confirm each remote client still launches. Core + the
   package PRs merge together (core-first breaks the launchers).

## Open questions for review

1. **Launcher scope per package.** Today one package can expose several launch
   surfaces (sunshine: `sunshine.open`, `pair-moonlight`, `moonlight.open`).
   Should `remote_client` be a single launcher that takes a subcommand
   (`open`/`pair`/…), or a map of named launchers? Lean: single script +
   `$EVE_REMOTE_ACTION` arg (mirrors how the TUI already passes an action id).
2. **Where moonlight's config + launcher live** — on the sunshine manifest
   directly, or a sunshine-owned `_clients` subpackage? Lean: directly on
   sunshine (it already declares the `pair-moonlight`/`moonlight` actions).
3. **`incompatible_with_bundles` vs extending `compatibility`** — add a sibling
   field, or widen the existing matrix to express bundle membership rules?
   Lean: sibling field (keeps the platform matrix focused on platform/desktop).
4. **Profile-resolve env contract** — the launchers read many resolved env vars
   by name today. Confirm the package launcher may rely on the full
   `profile-resolve` env being exported (not a trimmed `EVE_REMOTE_*` subset).
