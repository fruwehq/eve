# Remote Desktop Compatibility

This matrix documents the supported remote desktop combinations for v3 package
selection. It is intentionally conservative: `supported` means the package is
expected to be usable after provisioning; `wip` means the path exists or is a
target but still needs implementation or live validation; `unsupported` means
the package should not be offered as a working combination.

## Matrix

| Package | Platform | Desktop | Session/display | Status | Notes |
|---|---|---|---|---|---|
| `rdp` | Windows | Windows | Native | supported | Uses the built-in Windows RDP service. |
| `rdp` | Ubuntu | XFCE | X11 | supported | Uses `xrdp`/`xorgxrdp` with an isolated XFCE session. |
| `rdp` | Ubuntu | GNOME | Wayland | supported | Uses GNOME Remote Desktop system RDP with credentials. |
| `vnc` | Ubuntu | XFCE | X11 | supported | Uses TigerVNC on display `:1` with XFCE. |
| `vnc` | Ubuntu | GNOME | Wayland | unsupported | TigerVNC does not serve the local GNOME Wayland session. |
| `rustdesk` | Windows | Windows | Native | supported | Runs as a service against the active Windows desktop. |
| `rustdesk` | Ubuntu | XFCE | X11 | supported | Uses LightDM autologin plus an X11 desktop session. |
| `rustdesk` | Ubuntu | GNOME | Wayland | unsupported | RustDesk cannot unattended-share GNOME Wayland without peer-side screen selection. |
| `sunshine` | Windows | VDD | Native | supported | Uses Virtual Display Driver as the intended single Sunshine display. |
| `sunshine` | Ubuntu | XFCE | X11 | wip | Current Linux path uses X11 capture; ultrawide `5120x1440` still needs live validation. |
| `sunshine` | Ubuntu | GNOME | Wayland | wip | Wayland capture is not the stable default path yet. |
| `thinlinc` | Ubuntu amd64 | XFCE | X11 | supported | Stable ThinLinc session path. |
| `thinlinc` | Ubuntu amd64 | GNOME | X11 | wip | GNOME can run as a ThinLinc X11 session, but this path still needs validation. |
| `thinlinc` | Ubuntu amd64 | GNOME | Wayland | unsupported | ThinLinc serves X11 sessions, not the local GNOME Wayland compositor. |
| `waypipe` | Ubuntu amd64/arm64 | GNOME/app session | Wayland | wip | Wayland app forwarding, not a polished full desktop yet. |
| `xpra` | Ubuntu amd64 | XFCE/app session | X11 | legacy | Limited to Ubuntu 22.04/24.04; not an Ubuntu 26 path. |
| `xpra` | Windows amd64 | Windows | Native | wip | Available as an experimental package only. |

## Selection Rules

- X11 and Wayland packages can be installed on the same OS, but each remote
  desktop backend owns its own session assumptions. Do not treat one running
  desktop as proof that every remote backend can capture it.
- Prefer supported rows in the matrix when building bundles and platform
  defaults. WIP rows should stay opt-in until a live integration test confirms
  the specific provider, OS, desktop, and remote client.
- Eve and `package-list` enforce the current official GNOME/Wayland remote
  desktop policy: when `gnome-desktop` is selected, `rdp` is the only supported
  unattended remote desktop package. RustDesk, Sunshine, ThinLinc, VNC, and
  Waypipe remain visible as packages but are disabled for that desktop/session
  choice until they have a proven supported path.
- GNOME Wayland is the preferred modern desktop target. RDP uses GNOME Remote
  Desktop system mode for that path; VNC, RustDesk, and ThinLinc still use
  separate X11 sessions or are disabled for GNOME Wayland.
- RustDesk is disabled for GNOME desktop selections because GNOME Wayland asks
  the peer side to choose a screen, which breaks unattended access.
- ThinLinc is amd64-only in this project because the packaged server bundle is
  only installed for amd64.
- VNC and xrdp use isolated X11/XFCE sessions. They do not expose the local
  GNOME Wayland session.
- Windows Sunshine should keep VDD as the intended single active display for
  high-resolution/high-FPS streaming.

## Metadata

The package manifests expose this matrix through the optional `compatibility`
field. Remote desktop packages also set `compatibility_enforced: true`, so
`package-list` and Eve derive supported package combinations from manifest data
instead of hard-coded package lists. `scripts/catalog-options --json` includes
that metadata, and Eve renders it in the New Instance content step when a
package is highlighted.
