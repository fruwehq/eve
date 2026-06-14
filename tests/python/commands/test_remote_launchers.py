"""Behavior parity for the remote-* GUI launchers (Phase 2 bash->Python port).

Two layers:
1. subprocess-driven usage/missing-arg checks — assert each launcher prints a
   clean ``Usage:`` line to stderr and exits 2 before touching profile-resolve
   or instance-ip (so no live instance is required).
2. command-vector assertions against the builder functions in
   ``eve_sdk.remote_launch`` — assert each launcher builds the exact external
   client argv (moonlight, xfreerdp, vncviewer, waypipe, xpra attach, etc.)
   WITHOUT exec'ing it, covering env-knob handling, validation, and per-OS
   dispatch. No GUI client is launched and no SSH is performed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from eve_sdk import remote_launch as rl


@pytest.fixture(autouse=True)
def _scrub_ephemeral_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every command-vector test hermetic.

    The launcher builders read EPHEMERAL_* env knobs. Under the full `make test`
    run these can be present in the inherited environment (e.g. config-derived
    vars from `config-env --shell`, or a prior suite that exports
    EPHEMERAL_DISPLAY_RESOLUTION), which would non-deterministically perturb the
    "base" command-vector assertions. Clear them up front; tests that exercise a
    specific knob set it themselves afterwards via monkeypatch.
    """
    for key in list(os.environ):
        if key.startswith("EPHEMERAL_"):
            monkeypatch.delenv(key, raising=False)

ROOT = Path(__file__).resolve().parents[3]


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


# ======================== usage / missing-arg exit codes ================== #
@pytest.mark.parametrize(
    "script, usage",
    [
        ("remote-console", "Usage: scripts/remote-console <instance>"),
        ("remote-moonlight", "Usage: scripts/remote-moonlight <instance>"),
        ("remote-moonlight-pair", "Usage: scripts/remote-moonlight-pair <instance>"),
        ("remote-rdp", "Usage: scripts/remote-rdp <instance>"),
        ("remote-sunshine-wait", "Usage: scripts/remote-sunshine-wait <instance>"),
        ("remote-thinlinc", "Usage: scripts/remote-thinlinc <instance>"),
        ("remote-thinlinc-client", "Usage: scripts/remote-thinlinc-client <instance>"),
        ("remote-vnc", "Usage: scripts/remote-vnc <instance>"),
        (
            "remote-waypipe",
            "Usage: scripts/remote-waypipe <instance> [app [args...]]",
        ),
        (
            "remote-xpra",
            "Usage: scripts/remote-xpra <instance> <start|stop|run|attach|apps|status> [args...]",
        ),
    ],
)
def test_missing_arg_prints_usage_and_exits_2(script: str, usage: str) -> None:
    result = _run(script)
    assert result.returncode == 2
    assert usage in result.stderr
    assert result.stdout == ""


def test_remote_rustdesk_missing_arg_prints_usage_and_exits_2() -> None:
    result = _run("remote-rustdesk")
    assert result.returncode == 2
    assert "Usage: scripts/remote-rustdesk <instance> [connect]" in result.stderr
    assert "Prints the RustDesk connection details" in result.stderr


def test_remote_xpra_missing_action_exits_2() -> None:
    result = _run("remote-xpra", "some-instance")
    assert result.returncode == 2
    assert "Usage: scripts/remote-xpra" in result.stderr


# ======================== moonlight command vector ======================== #
def test_moonlight_stream_command_base() -> None:
    cmd = rl.moonlight_stream_command("10.0.0.5")
    assert cmd == [
        "/Applications/Moonlight.app/Contents/MacOS/Moonlight", "stream",
        "--game-optimization", "10.0.0.5", "Desktop",
    ]


def test_moonlight_stream_command_with_env_knobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHEMERAL_DISPLAY_RESOLUTION", "2560x1440")
    monkeypatch.setenv("EPHEMERAL_DISPLAY_FPS", "120")
    monkeypatch.setenv("EPHEMERAL_MOONLIGHT_BITRATE_KBPS", "50000")
    monkeypatch.setenv("EPHEMERAL_MOONLIGHT_DISPLAY_MODE", "borderless")
    monkeypatch.setenv("EPHEMERAL_MOONLIGHT_VIDEO_CODEC", "HEVC")
    monkeypatch.setenv("EPHEMERAL_MOONLIGHT_VIDEO_DECODER", "hardware")
    cmd = rl.moonlight_stream_command("10.0.0.5")
    assert cmd == [
        "/Applications/Moonlight.app/Contents/MacOS/Moonlight", "stream",
        "--game-optimization",
        "--resolution", "2560x1440",
        "--fps", "120",
        "--bitrate", "50000",
        "--display-mode", "borderless",
        "--video-codec", "HEVC",
        "--video-decoder", "hardware",
        "10.0.0.5", "Desktop",
    ]


@pytest.mark.parametrize(
    "env_var, value",
    [
        ("EPHEMERAL_MOONLIGHT_DISPLAY_MODE", "weird"),
        ("EPHEMERAL_MOONLIGHT_VIDEO_CODEC", "MPEG2"),
        ("EPHEMERAL_MOONLIGHT_VIDEO_DECODER", "quantum"),
    ],
)
def test_moonlight_invalid_env_exits_2(
    env_var: str, value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(env_var, value)
    with pytest.raises(SystemExit) as exc:
        rl.moonlight_stream_command("1.2.3.4")
    assert exc.value.code == 2


# ======================== moonlight-pair vectors ========================== #
def test_moonlight_pair_command() -> None:
    assert rl.moonlight_pair_command("10.0.0.5", "1234") == [
        "/Applications/Moonlight.app/Contents/MacOS/Moonlight", "pair",
        "--pin", "1234", "10.0.0.5",
    ]


def test_sunshine_pair_curl_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHEMERAL_SUNSHINE_PASSWORD", "s3cret")
    cmd = rl.sunshine_pair_curl_command("10.0.0.5", "1234", "/tmp/r.json")
    assert cmd == [
        "curl", "-sS", "-i", "-k",
        "-u", "sunshine:s3cret",
        "-H", "Content-Type: application/json",
        "--data-binary", '{"pin":"1234","name":"ephemeral-client"}',
        "-o", "/tmp/r.json",
        "-w", "%{http_code}",
        "https://10.0.0.5:47990/api/pin",
    ]


# ======================== sunshine-wait vector ============================ #
def test_sunshine_config_curl_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHEMERAL_SUNSHINE_PASSWORD", "pw")
    cmd = rl.sunshine_config_curl_command("10.0.0.5")
    assert cmd == [
        "curl", "-sS", "-k", "-L",
        "-u", "sunshine:pw",
        "-o", "/dev/null",
        "-w", "%{http_code}",
        "https://10.0.0.5:47990/api/config",
    ]


# ======================== rdp vectors ===================================== #
def test_rdp_file_lines() -> None:
    lines = rl.rdp_file_lines("10.0.0.5", "Administrator", 1, 0, 1)
    assert lines == [
        "full address:s:10.0.0.5",
        "username:s:Administrator",
        "prompt for credentials on client:i:1",
        "enablecredsspsupport:i:1",
        "use redirection server name:i:0",
        "administrative session:i:1",
        "screen mode id:i:2",
        "session bpp:i:32",
        "redirectclipboard:i:1",
        "audiomode:i:0",
    ]


def test_xfreerdp_command() -> None:
    assert rl.xfreerdp_command("10.0.0.5", "user", "pw", ["/gfx:AVC444"]) == [
        "xfreerdp", "/v:10.0.0.5", "/u:user", "/p:pw", "+clipboard", "/cert:ignore", "/gfx:AVC444",
    ]


def test_msrdp_open_and_paste_commands() -> None:
    assert rl.msrdp_open_command("tmp/windows.rdp") == [
        "open", "-a", "Microsoft Remote Desktop", "tmp/windows.rdp",
    ]
    assert rl.msrdp_paste_command()[0] == "osascript"
    assert "key code 36" in rl.msrdp_paste_command()[-1]


# ======================== rustdesk vector ================================= #
def test_rustdesk_connect_command_without_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUSTDESK_PASSWORD", raising=False)
    assert rl.rustdesk_connect_command("rustdesk", "123456789") == [
        "rustdesk", "--connect", "123456789",
    ]


def test_rustdesk_connect_command_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUSTDESK_PASSWORD", "hunter2")
    assert rl.rustdesk_connect_command("rustdesk", "123456789") == [
        "rustdesk", "--connect", "123456789", "--password", "hunter2",
    ]


# ======================== thinlinc vectors ================================ #
def test_thinlinc_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THINLINC_WEBACCESS_PORT", raising=False)
    assert rl.thinlinc_url("10.0.0.5") == "https://10.0.0.5:300"
    monkeypatch.setenv("THINLINC_WEBACCESS_PORT", "443")
    assert rl.thinlinc_url("10.0.0.5") == "https://10.0.0.5:443"


def test_thinlinc_client_args_and_commands() -> None:
    assert rl.thinlinc_client_args("10.0.0.5", "eve") == ["-u", "eve", "10.0.0.5"]
    assert rl.thinlinc_client_args("10.0.0.5", "") == ["10.0.0.5"]
    assert rl.thinlinc_client_macos_command(["-u", "eve", "1.2.3.4"]) == [
        "open", "-a", "ThinLinc Client", "--args", "-u", "eve", "1.2.3.4",
    ]
    assert rl.thinlinc_client_linux_command(["-u", "eve", "1.2.3.4"]) == [
        "tlclient", "-u", "eve", "1.2.3.4",
    ]


def test_url_open_command() -> None:
    assert rl.url_open_command("open", "https://x:300") == ["open", "https://x:300"]


# ======================== vnc vectors ===================================== #
def test_vnc_tunnel_opts_and_command() -> None:
    assert rl.vnc_tunnel_opts_vagrant("2222", "/k/id") == [
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-p", "2222", "-i", "/k/id",
    ]
    assert rl.vnc_tunnel_opts_terraform("/k/id") == [
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ServerAliveInterval=10", "-i", "/k/id",
    ]
    assert rl.vnc_tunnel_opts_terraform("") == [
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ServerAliveInterval=10",
    ]
    assert rl.vnc_tunnel_command("15900", "5901", "ubuntu@1.2.3.4", ["-i", "/k"]) == [
        "ssh", "-f", "-N", "-L", "15900:127.0.0.1:5901", "-i", "/k", "ubuntu@1.2.3.4",
    ]


def test_vnc_viewer_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VNC_DESKTOP_SIZE", raising=False)
    assert rl.vnc_viewer_args() == [
        "-Shared", "-AcceptClipboard", "-SendClipboard",
        "-RemoteResize=0", "-AlwaysCursor=1", "-CursorType=System",
    ]
    monkeypatch.setenv("VNC_DESKTOP_SIZE", "1920x1080")
    assert rl.vnc_viewer_args()[-2:] == ["-DesktopSize", "1920x1080"]


def test_vncviewer_and_system_commands() -> None:
    assert rl.vncviewer_command(["-Shared"], ["-passwd", "/p"], "15900") == [
        "vncviewer", "-Shared", "-passwd", "/p", "127.0.0.1::15900",
    ]
    assert rl.vnc_system_open_command("vagrant", "15900") == [
        "open", "vnc://:vagrant@127.0.0.1:15900",
    ]


# ======================== waypipe vectors ================================= #
def test_waypipe_commands() -> None:
    assert rl.waypipe_vagrant_command("/tmp/cfg", ["foot"]) == [
        "waypipe", "ssh", "-o", "StreamLocalBindUnlink=yes", "-F", "/tmp/cfg", "default", "foot",
    ]
    assert rl.waypipe_ssh_command(["-o", "X=y"], "ubuntu@1.2.3.4", ["foot"]) == [
        "waypipe", "ssh", "-o", "X=y", "ubuntu@1.2.3.4", "foot",
    ]
    assert rl.waypipe_ssh_opts("/k/id") == [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex", "-o", "StreamLocalBindUnlink=yes",
        "-i", "/k/id", "-o", "IdentitiesOnly=yes",
    ]
    assert rl.waypipe_ssh_opts("") == [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex", "-o", "StreamLocalBindUnlink=yes",
    ]


# ======================== xpra vectors ==================================== #
def test_xpra_ssh_opts() -> None:
    assert rl.xpra_ssh_opts("/k/id", "2222") == [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex", "-i", "/k/id", "-p", "2222",
    ]
    assert rl.xpra_ssh_opts("", "22") == [
        "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=10",
        "-o", "WarnWeakCrypto=no-pq-kex",
    ]


def test_xpra_attach_commands() -> None:
    assert rl.xpra_attach_linux_command("ssh://u@h/100", "ssh -o X=y") == [
        "xpra", "attach", "ssh://u@h/100", "--ssh=ssh -o X=y", "--clipboard=yes",
    ]
    assert rl.xpra_attach_windows_command("tcp://localhost:14500") == [
        "xpra", "attach", "tcp://localhost:14500", "--desktop-fullscreen=yes", "--clipboard=yes",
    ]
    assert rl.xpra_attach_desktop_command("ssh://u@h/101", "ssh -o X=y") == [
        "xpra", "attach", "ssh://u@h/101", "--ssh=ssh -o X=y",
        "--desktop-fullscreen=no", "--desktop-scaling=1", "--clipboard=yes",
    ]
    assert rl.xpra_tunnel_command("14500", ["-o", "X=y"], "Administrator", "1.2.3.4") == [
        "ssh", "-o", "X=y", "-l", "Administrator", "-N",
        "-L", "14500:127.0.0.1:14500", "1.2.3.4",
    ]


# ======================== shared helpers ================================== #
def test_has_package() -> None:
    assert rl.has_package({"BUNDLE_PACKAGES": "sunshine,foo"}, "sunshine")
    assert rl.has_package({"BUNDLE_PACKAGES": "foo,sunshine"}, "sunshine")
    assert not rl.has_package({"BUNDLE_PACKAGES": "foo,bar"}, "sunshine")
    assert not rl.has_package({"BUNDLE_PACKAGES": ""}, "sunshine")
    assert not rl.has_package({}, "sunshine")


def test_validate_unix_user_rejects_bad_names() -> None:
    rl.validate_unix_user("eve", "remote-vnc")
    rl.validate_unix_user("eve-test_2.0", "remote-vnc")
    with pytest.raises(SystemExit) as exc:
        rl.validate_unix_user("bad name", "remote-vnc")
    assert exc.value.code == 2


def test_resolve_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSH_PUBLIC_KEY_FILE", "/keys/id.pub")
    assert rl.resolve_private_key() == "/keys/id"
    monkeypatch.setenv("SSH_PUBLIC_KEY_FILE", "/keys/noext")
    monkeypatch.setenv("SSH_PRIVATE_KEY_FILE", "/keys/priv")
    assert rl.resolve_private_key() == "/keys/priv"
    monkeypatch.delenv("SSH_PUBLIC_KEY_FILE", raising=False)
    assert rl.resolve_private_key() == "/keys/priv"


def test_shell_quote() -> None:
    assert rl.shell_quote("simple") == "'simple'"
    assert rl.shell_quote("it's") == "'it'\\''s'"
