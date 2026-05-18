# Remote Desktop Compatibility

This matrix documents the supported remote desktop combinations for v3 package
selection. It is intentionally conservative: `supported` means the package is
expected to be usable after provisioning; `wip` means the path exists or is a
target but still needs implementation or live validation; `unsupported` means
the package should not be offered as a working combination.

## Desktop Modes

Eve models the Linux desktop as one active desktop/session mode per instance.
The desktop packages set `conflicts_with` in their manifests, and
`instance-resolve`, `package-list`, and Eve use that metadata to prevent
accidentally selecting multiple desktops together.

| Bundle | Desktop package | RDP backend | Display/session | Status | Notes |
|---|---|---|---|---|---|
| `desktop-xfce` | `xfce-desktop` | `xrdp`/`xorgxrdp` | XFCE / X11 | supported | LightDM autologin with a local graphical session. |
| `desktop-xfce-headless` | `xfce-desktop-headless` | `xrdp`/`xorgxrdp` | XFCE Headless / X11 | supported | No local display manager; locks and power management disabled. |
| `desktop-gnome` | `gnome-desktop` | GNOME Remote Desktop | GNOME / Wayland | supported | GDM autologin and per-user GNOME Remote Desktop credentials. |
| `desktop-gnome-headless` | `gnome-desktop-headless` | GNOME Remote Desktop | GNOME Headless / Wayland | supported | Uses GNOME virtual monitor support when available. |
| `desktop-kde` | `kde-desktop` | `krdp` | KDE Plasma / Wayland | supported | FreeRDP with `/gfx:AVC444` is recommended; macOS Windows App may not work. |
| `desktop-kde-headless` | `kde-desktop-headless` | `krdp` | KDE Plasma Headless / Wayland | supported | Lock and power management are disabled for unattended `krdp`. |

## Remote Package Matrix

| Package | Platform | Desktop | Session/display | Status | Notes |
|---|---|---|---|---|---|
| `rdp` | Windows | Windows | Native | supported | Uses the built-in Windows RDP service. |
| `rdp` | Ubuntu | XFCE | X11 | supported | Uses `xrdp`/`xorgxrdp`. |
| `rdp` | Ubuntu | XFCE Headless | X11 | supported | Uses `xrdp`/`xorgxrdp` without a local display manager. |
| `rdp` | Ubuntu | GNOME | Wayland | supported | Uses GNOME Remote Desktop per-user RDP with gate credentials. |
| `rdp` | Ubuntu | GNOME Headless | Wayland | supported | Uses GNOME Remote Desktop with virtual monitor support. |
| `rdp` | Ubuntu | KDE Plasma | Wayland | supported | Uses `krdp`; prefer FreeRDP with `/gfx:AVC444`. |
| `rdp` | Ubuntu | KDE Plasma Headless | Wayland | supported | Uses `krdp` with unattended lock/power settings. |
| `vnc` | Ubuntu | XFCE | X11 | supported | Uses TigerVNC on display `:1` with XFCE. |
| `vnc` | Ubuntu | XFCE Headless | X11 | supported | Uses TigerVNC on display `:1` with XFCE. |
| `vnc` | Ubuntu | GNOME/KDE | Wayland | unsupported | TigerVNC does not serve local Wayland compositor sessions. |
| `rustdesk` | Windows | Windows | Native | supported | Runs as a service against the active Windows desktop. |
| `rustdesk` | Ubuntu | XFCE | X11 | supported | Uses LightDM autologin plus an X11 desktop session. |
| `rustdesk` | Ubuntu | XFCE Headless | X11 | unsupported | RustDesk needs an active local desktop session; use RDP. |
| `rustdesk` | Ubuntu | GNOME/KDE | Wayland | unsupported | Unattended Wayland sharing requires peer-side screen selection or is not proven. |
| `sunshine` | Windows | VDD | Native | supported | Uses Virtual Display Driver as the intended single Sunshine display. |
| `sunshine` | Ubuntu | XFCE | X11 | wip | Linux capture exists, but ultrawide `5120x1440` still needs live validation. |
| `sunshine` | Ubuntu | XFCE Headless | X11 | wip | Linux capture exists, but ultrawide `5120x1440` still needs live validation. |
| `sunshine` | Ubuntu | GNOME | Wayland | wip | Wayland capture is not the stable default path yet. |
| `thinlinc` | Ubuntu amd64 | XFCE | X11 | supported | Stable ThinLinc session path. |
| `thinlinc` | Ubuntu amd64 | XFCE Headless | X11 | supported | Stable ThinLinc session path without local display manager. |
| `thinlinc` | Ubuntu amd64 | GNOME | X11 | wip | GNOME can run as a ThinLinc X11 session, but this path still needs validation. |
| `thinlinc` | Ubuntu amd64 | GNOME | Wayland | unsupported | ThinLinc serves X11 sessions, not the local GNOME Wayland compositor. |
| `waypipe` | Ubuntu amd64/arm64 | GNOME/app session | Wayland | wip | Wayland app forwarding, not a polished full desktop yet. |
| `xpra` | Ubuntu amd64 | XFCE/app session | X11 | legacy | Limited to Ubuntu 22.04/24.04; not an Ubuntu 26 path. |
| `xpra` | Windows amd64 | Windows | Native | wip | Available as an experimental package only. |

## Selection Rules

- Pick one desktop mode per instance. XFCE, GNOME, KDE, and their headless
  variants are mutually exclusive through manifest metadata.
- Prefer supported rows in the matrix when building bundles and platform
  defaults. WIP rows stay opt-in until live integration confirms the provider,
  OS, desktop, and remote client.
- X11 and Wayland packages can coexist on the OS, but each remote backend owns
  its own session assumptions. A working desktop in one backend does not prove
  every backend can capture it.
- GNOME Wayland uses GNOME Remote Desktop for unattended RDP. VNC, RustDesk,
  and ThinLinc do not expose the local GNOME Wayland compositor.
- KDE Wayland uses `krdp`. The reference path is FreeRDP with `/gfx:AVC444`;
  macOS Windows App compatibility is not assumed.
- Windows Sunshine should keep VDD as the intended single active display for
  high-resolution/high-FPS streaming.

## Metadata

The package manifests expose this matrix through the optional `compatibility`
field. Remote desktop packages also set `compatibility_enforced: true`, so
`package-list` and Eve derive supported package combinations from manifest data
instead of hard-coded package lists. Desktop packages expose `conflicts_with`
metadata so mutually exclusive desktop modes are enforced from configuration.
`scripts/catalog-options --json` includes both metadata sets, and Eve renders
compatibility details in the New Instance content step when a package is
highlighted.
