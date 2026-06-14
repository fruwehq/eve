"""Shared helpers for the remote-* GUI launcher scripts.

These launchers share a common spine — resolve the profile env, locate the
instance IP, validate the remote unix user, resolve the SSH private key, and
check bundle membership — and each builds a client command vector (moonlight,
xfreerdp, vncviewer, waypipe, xpra, etc.) that it then execs. The command
vectors are constructed by the testable builder functions in this module so the
launchers can be parity-checked without launching a GUI.

Scripts these call that are still bash (profile-resolve, instance-ssh,
instance-ip, ssh-wait, vagrant-up) stay as subprocess calls.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Mirrors the bash ``case "$user" in *[!a-zA-Z0-9._-]*)`` guard used by
# remote-vnc and remote-sunshine-wait.
_UNIX_USER_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# Fixed client paths the launchers exec verbatim.
_MOONLIGHT_APP = "/Applications/Moonlight.app/Contents/MacOS/Moonlight"
_RUSTDESK_APP = "/Applications/RustDesk.app/Contents/MacOS/rustdesk"

# Validated moonlight env knobs.
_MOONLIGHT_DISPLAY_MODES = {"fullscreen", "borderless", "windowed"}
_MOONLIGHT_VIDEO_CODECS = {"auto", "H.264", "HEVC", "AV1"}
_MOONLIGHT_VIDEO_DECODERS = {"auto", "hardware", "software"}


# ============================ shared infrastructure ======================== #
def repo_root() -> Path:
    """Return ``git rev-parse --show-toplevel`` (errors propagate as under set -e)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return Path(result.stdout.strip())


def resolve_env(root: Path, profile: str) -> dict[str, str]:
    """Resolve a profile to a KEY=value env dict via scripts/profile-resolve.

    Mirrors ``RESOLVED_ENV=$(./scripts/profile-resolve ...)``: stderr passes
    through, exit status propagates (set -e on the command substitution).
    """
    result = subprocess.run(
        [str(root / "scripts/profile-resolve"), "--profile", profile, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def instance_ip(root: Path, profile: str) -> str:
    """Return the instance IP via scripts/instance-ip.

    Mirrors ``IP=$(./scripts/instance-ip "$PROFILE")``: stderr passes through,
    exit status propagates under set -e.
    """
    result = subprocess.run(
        [str(root / "scripts/instance-ip"), profile],
        cwd=root, text=True, capture_output=True, check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def has_package(resolved: dict[str, str], package: str) -> bool:
    """Return True if ``package`` is a member of the resolved BUNDLE_PACKAGES list.

    Mirrors ``echo "$PKGS" | tr ',' '\\n' | grep -qx <package>`` and the RDP
    ``case ",$BUNDLE_PACKAGES," in *,"$1",*)`` helper — both exact token matches.
    """
    pkgs = resolved.get("BUNDLE_PACKAGES", "")
    return package in pkgs.split(",")


def validate_unix_user(name: str, script: str) -> None:
    """Mirror the bash ``case "$user" in *[!a-zA-Z0-9._-]*)`` guard.

    Exits 2 with a clean message to stderr when the name contains characters
    outside the allowed unix-user set.
    """
    if not _UNIX_USER_RE.fullmatch(name):
        print(f"{script}: unsupported VM user name: {name}", file=sys.stderr)
        raise SystemExit(2)


def resolve_private_key() -> str:
    """Resolve the SSH private key path from env, matching the bash convention.

    Mirrors::

        KEY_FILE="${SSH_PUBLIC_KEY_FILE:-}"
        if [ -n "$KEY_FILE" ] && [ "${KEY_FILE%.pub}" != "$KEY_FILE" ]; then
          PRIV_KEY="${KEY_FILE%.pub}"
        else
          PRIV_KEY="${SSH_PRIVATE_KEY_FILE:-}"
        fi
    """
    key_file = os.environ.get("SSH_PUBLIC_KEY_FILE", "")
    if key_file and key_file.endswith(".pub"):
        return key_file[:-4]
    return os.environ.get("SSH_PRIVATE_KEY_FILE", "")


def shell_quote(value: str) -> str:
    """Quote a string for a POSIX shell, single-quote style.

    Mirrors the bash ``shell_quote`` helper used by remote-rustdesk: wrap in
    single quotes and replace embedded single quotes with ``'\\''``.
    """
    return "'" + value.replace("'", "'\\''") + "'"


def instance_workdir(root: Path, instance: str) -> str:
    """Resolve ``INSTANCE_WORKDIR`` via scripts/instance-paths.

    Mirrors the bash ``eve_instance_workdir`` helper in lib/instance-workdir.sh:
    propagate instance-paths stderr + exit status, then extract the
    INSTANCE_WORKDIR value (everything after the first ``=``).
    """
    result = subprocess.run(
        [str(root / "scripts/instance-paths"), "--instance", instance, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    for line in result.stdout.splitlines():
        if line.startswith("INSTANCE_WORKDIR="):
            return line.split("=", 1)[1]
    print(
        "instance-workdir: INSTANCE_WORKDIR missing from scripts/instance-paths output",
        file=sys.stderr,
    )
    raise SystemExit(1)


def vagrant_ssh_config(workdir: str) -> str:
    """Return ``vagrant ssh-config`` output run inside ``workdir``."""
    result = subprocess.run(
        ["vagrant", "ssh-config"], cwd=workdir, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout


def ssh_config_field(config: str, field: str) -> str:
    """Extract the first value of ``field`` from an ssh-config block.

    Mirrors ``vagrant ssh-config | awk '/<field>/ {print $2; exit}'``.
    """
    for line in config.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == field:
            return parts[1]
    return ""


def shutil_which(name: str) -> str | None:
    """Return the absolute path to ``name`` on PATH, or None (mirrors command -v)."""
    from shutil import which
    return which(name)


def has_command(name: str) -> bool:
    """Mirror ``command -v <name> >/dev/null 2>&1``."""
    return shutil_which(name) is not None


def exec_replace(cmd: list[str]) -> int:
    """Mirror bash ``exec <cmd>``: replace the current process with ``cmd``.

    On a missing executable, print a clean error and exit 127 like bash.
    """
    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError:
        print(f"{cmd[0]}: command not found", file=sys.stderr)
        raise SystemExit(127) from None
    return 0  # unreachable — exec replaces the process


# ============================ command-vector builders ====================== #
# Each builder constructs the exact external client argv the launcher execs,
# without running it. Tests assert the vectors directly.

# ---- remote-moonlight ----------------------------------------------------- #
def moonlight_stream_command(ip: str) -> list[str]:
    """Build the Moonlight ``stream`` argv from EPHEMERAL_* env knobs.

    Exits 2 with a clean message on an invalid env value, matching the bash
    case-validation guards. The base argv is::

        Moonlight stream --game-optimization [<extra>] <ip> Desktop
    """
    cmd = [_MOONLIGHT_APP, "stream", "--game-optimization"]
    res = os.environ.get("EPHEMERAL_DISPLAY_RESOLUTION", "")
    if res:
        cmd += ["--resolution", res]
    fps = os.environ.get("EPHEMERAL_DISPLAY_FPS", "")
    if fps:
        cmd += ["--fps", fps]
    bitrate = os.environ.get("EPHEMERAL_MOONLIGHT_BITRATE_KBPS", "")
    if bitrate:
        cmd += ["--bitrate", bitrate]
    mode = os.environ.get("EPHEMERAL_MOONLIGHT_DISPLAY_MODE", "")
    if mode:
        if mode not in _MOONLIGHT_DISPLAY_MODES:
            print(
                f"remote-moonlight: invalid EPHEMERAL_MOONLIGHT_DISPLAY_MODE='{mode}' "
                "(valid: fullscreen, borderless, windowed)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        cmd += ["--display-mode", mode]
    codec = os.environ.get("EPHEMERAL_MOONLIGHT_VIDEO_CODEC", "")
    if codec:
        if codec not in _MOONLIGHT_VIDEO_CODECS:
            print(
                f"remote-moonlight: invalid EPHEMERAL_MOONLIGHT_VIDEO_CODEC='{codec}' "
                "(valid: auto, H.264, HEVC, AV1)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        cmd += ["--video-codec", codec]
    decoder = os.environ.get("EPHEMERAL_MOONLIGHT_VIDEO_DECODER", "")
    if decoder:
        if decoder not in _MOONLIGHT_VIDEO_DECODERS:
            print(
                f"remote-moonlight: invalid EPHEMERAL_MOONLIGHT_VIDEO_DECODER='{decoder}' "
                "(valid: auto, hardware, software)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        cmd += ["--video-decoder", decoder]
    cmd += [ip, "Desktop"]
    return cmd


# ---- remote-moonlight-pair ------------------------------------------------ #
def moonlight_pair_command(ip: str, pin: str) -> list[str]:
    """Build the Moonlight ``pair`` argv: ``Moonlight pair --pin <pin> <ip>``."""
    return [_MOONLIGHT_APP, "pair", "--pin", pin, ip]


def sunshine_pair_curl_command(ip: str, pin: str, response_file: str) -> list[str]:
    """Build the curl argv that submits the pairing PIN to the Sunshine API."""
    password = os.environ.get("EPHEMERAL_SUNSHINE_PASSWORD", "")
    return [
        "curl", "-sS", "-i", "-k",
        "-u", f"sunshine:{password}",
        "-H", "Content-Type: application/json",
        "--data-binary", f'{{"pin":"{pin}","name":"ephemeral-client"}}',
        "-o", response_file,
        "-w", "%{http_code}",
        f"https://{ip}:47990/api/pin",
    ]


# ---- remote-sunshine-wait ------------------------------------------------- #
def sunshine_config_curl_command(ip: str) -> list[str]:
    """Build the curl argv that probes the Sunshine config API readiness."""
    password = os.environ.get("EPHEMERAL_SUNSHINE_PASSWORD", "")
    return [
        "curl", "-sS", "-k", "-L",
        "-u", f"sunshine:{password}",
        "-o", "/dev/null",
        "-w", "%{http_code}",
        f"https://{ip}:47990/api/config",
    ]


# ---- remote-rdp ----------------------------------------------------------- #
def rdp_file_lines(
    ip: str, username: str, credssp: int, redirect: int, admin_session: int,
) -> list[str]:
    """Build the line list written to ./tmp/windows.rdp.

    Order and field names are preserved verbatim from the bash ``printf`` block.
    """
    return [
        f"full address:s:{ip}",
        f"username:s:{username}",
        "prompt for credentials on client:i:1",
        f"enablecredsspsupport:i:{credssp}",
        f"use redirection server name:i:{redirect}",
        f"administrative session:i:{admin_session}",
        "screen mode id:i:2",
        "session bpp:i:32",
        "redirectclipboard:i:1",
        "audiomode:i:0",
    ]


def xfreerdp_command(
    ip: str, username: str, password: str, extra: list[str],
) -> list[str]:
    """Build the ``xfreerdp`` argv::

        xfreerdp /v:<ip> /u:<user> /p:<pw> +clipboard /cert:ignore [<extra>...]
    """
    return [
        "xfreerdp", f"/v:{ip}", f"/u:{username}", f"/p:{password}",
        "+clipboard", "/cert:ignore", *extra,
    ]


def msrdp_open_command(rdp_file: str) -> list[str]:
    """Build the macOS ``open -a "Microsoft Remote Desktop"`` argv."""
    return ["open", "-a", "Microsoft Remote Desktop", rdp_file]


def msrdp_paste_command() -> list[str]:
    """Build the osascript argv that pastes + presses Enter via System Events."""
    return [
        "osascript",
        "-e", 'tell application "System Events" to keystroke "v" using command down',
        "-e", 'tell application "System Events" to key code 36',
    ]


# ---- remote-rustdesk ------------------------------------------------------ #
def rustdesk_local_client() -> str:
    """Resolve the local rustdesk client path, mirroring the bash candidate walk.

    Order: macOS .app binary (if Darwin + executable), then PATH/binary lookups
    for ``rustdesk`` and ``/usr/bin/rustdesk``. Returns "" when nothing is found.
    """
    import platform
    if platform.system() == "Darwin":
        app = _RUSTDESK_APP
        if os.access(app, os.X_OK):
            return app
    for candidate in ("rustdesk", "/usr/bin/rustdesk"):
        if shutil_which(candidate) is not None or os.access(candidate, os.X_OK):
            return candidate
    return ""


def rustdesk_connect_command(cli: str, rustdesk_id: str) -> list[str]:
    """Build the local rustdesk connect argv.

    ``--password <pw>`` is appended only when ``RUSTDESK_PASSWORD`` is set,
    mirroring ``${PASSWORD_ARG:+"$PASSWORD_ARG" "$RUSTDESK_PASSWORD"}``.
    """
    cmd = [cli, "--connect", rustdesk_id]
    password = os.environ.get("RUSTDESK_PASSWORD", "")
    if password:
        cmd += ["--password", password]
    return cmd


# ---- remote-thinlinc ------------------------------------------------------ #
def thinlinc_url(ip: str) -> str:
    """Build the ThinLinc Web Access URL ``https://<ip>:<port>``.

    ``THINLINC_WEBACCESS_PORT`` overrides the default 300.
    """
    port = os.environ.get("THINLINC_WEBACCESS_PORT", "300")
    return f"https://{ip}:{port}"


def url_open_command(opener: str, url: str) -> list[str]:
    """Build ``<opener> <url>`` for ``open`` / ``xdg-open``."""
    return [opener, url]


# ---- remote-thinlinc-client ----------------------------------------------- #
def thinlinc_client_args(ip: str, user_name: str) -> list[str]:
    """Build the shared tlclient args: optional ``-u <user>`` then ``<ip>``."""
    args: list[str] = []
    if user_name:
        args += ["-u", user_name]
    args.append(ip)
    return args


def thinlinc_client_macos_command(args: list[str]) -> list[str]:
    """Build the macOS ``open -a "ThinLinc Client" --args ...`` argv."""
    return ["open", "-a", "ThinLinc Client", "--args", *args]


def thinlinc_client_linux_command(args: list[str]) -> list[str]:
    """Build the Linux ``tlclient ...`` argv."""
    return ["tlclient", *args]


# ---- remote-vnc ----------------------------------------------------------- #
def vnc_tunnel_command(
    local_port: str, vnc_port: str, target: str, opts: list[str],
) -> list[str]:
    """Build the ``ssh -f -N -L`` tunnel argv for the VNC port forward."""
    return ["ssh", "-f", "-N", "-L", f"{local_port}:127.0.0.1:{vnc_port}", *opts, target]


def vnc_tunnel_opts_vagrant(ssh_port: str, priv_key: str) -> list[str]:
    """Build the vagrant ssh tunnel opts."""
    return [
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-p", ssh_port, "-i", priv_key,
    ]


def vnc_tunnel_opts_terraform(priv_key: str) -> list[str]:
    """Build the terraform ssh tunnel opts (with optional -i key)."""
    opts = [
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ServerAliveInterval=10",
    ]
    if priv_key:
        opts += ["-i", priv_key]
    return opts


def vnc_viewer_args() -> list[str]:
    """Build the TigerVNC viewer flags, including optional ``-DesktopSize``."""
    args = [
        "-Shared", "-AcceptClipboard", "-SendClipboard",
        "-RemoteResize=0", "-AlwaysCursor=1", "-CursorType=System",
    ]
    desktop_size = os.environ.get("VNC_DESKTOP_SIZE", "")
    if desktop_size:
        args += ["-DesktopSize", desktop_size]
    return args


def vncviewer_command(
    viewer_args: list[str], auth_args: list[str], local_port: str,
) -> list[str]:
    """Build the ``vncviewer <flags> <auth> 127.0.0.1::<port>`` argv."""
    return ["vncviewer", *viewer_args, *auth_args, f"127.0.0.1::{local_port}"]


def vnc_system_open_command(password: str, local_port: str) -> list[str]:
    """Build the macOS ``open vnc://:<pw>@127.0.0.1:<port>`` argv."""
    return ["open", f"vnc://:{password}@127.0.0.1:{local_port}"]


def vnc_passwd_fetch_command(vnc_user: str) -> str:
    """Build the remote shell command that fetches the VNC passwd file bytes."""
    return (
        f'home=$(getent passwd \'{vnc_user}\' | cut -d: -f6); '
        'if [ -f "$home/.config/tigervnc/passwd" ]; then '
        'sudo cat "$home/.config/tigervnc/passwd"; '
        'elif [ -f "$home/.vnc/passwd" ]; then '
        'sudo cat "$home/.vnc/passwd"; else exit 1; fi'
    )


# ---- remote-waypipe ------------------------------------------------------- #
def waypipe_vagrant_command(ssh_config: str, app: list[str]) -> list[str]:
    """Build the waypipe argv for a vagrant profile.

    ``waypipe ssh -o StreamLocalBindUnlink=yes -F <config> default <app...>``
    """
    return [
        "waypipe", "ssh", "-o", "StreamLocalBindUnlink=yes",
        "-F", ssh_config, "default", *app,
    ]


def waypipe_ssh_command(
    ssh_opts: list[str], target: str, app: list[str],
) -> list[str]:
    """Build the waypipe argv for a terraform/metal profile."""
    return ["waypipe", "ssh", *ssh_opts, target, *app]


def waypipe_ssh_opts(priv_key: str) -> list[str]:
    """Build the waypipe ssh opts (with optional -i key + IdentitiesOnly)."""
    opts = [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex", "-o", "StreamLocalBindUnlink=yes",
    ]
    if priv_key:
        opts += ["-i", priv_key, "-o", "IdentitiesOnly=yes"]
    return opts


# ---- remote-xpra ---------------------------------------------------------- #
def xpra_ssh_opts(priv_key: str, ssh_port: str) -> list[str]:
    """Build the xpra remote-ssh opts (with optional -i key and -p port)."""
    opts = [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex",
    ]
    if priv_key:
        opts += ["-i", priv_key]
    if ssh_port != "22":
        opts += ["-p", ssh_port]
    return opts


def xpra_attach_linux_command(uri: str, ssh_cmd: str) -> list[str]:
    """Build the Linux ``xpra attach <uri> --ssh=<cmd> --clipboard=yes`` argv."""
    return ["xpra", "attach", uri, f"--ssh={ssh_cmd}", "--clipboard=yes"]


def xpra_attach_windows_command(uri: str) -> list[str]:
    """Build the Windows ``xpra attach <uri> --desktop-fullscreen=yes`` argv."""
    return ["xpra", "attach", uri, "--desktop-fullscreen=yes", "--clipboard=yes"]


def xpra_attach_desktop_command(uri: str, ssh_cmd: str) -> list[str]:
    """Build the desktop ``xpra attach`` argv (fullscreen=no, scaling=1)."""
    return [
        "xpra", "attach", uri, f"--ssh={ssh_cmd}",
        "--desktop-fullscreen=no", "--desktop-scaling=1", "--clipboard=yes",
    ]


def xpra_tunnel_command(
    tcp_port: str, ssh_opts: list[str], ssh_user: str, ip: str,
) -> list[str]:
    """Build the Windows xpra ``ssh -N -L`` tunnel argv."""
    return [
        "ssh", *ssh_opts, "-l", ssh_user, "-N",
        "-L", f"{tcp_port}:127.0.0.1:{tcp_port}", ip,
    ]
