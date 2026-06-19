"""The TUI's command arg-builders emit script argv (no `make` layer) — v4.3 §3."""

from __future__ import annotations

from pathlib import Path

from tui import commands as c

SCRIPTS = Path(c.SCRIPTS)


def _tail(argv: list[str], n: int) -> list[str]:
    return argv[-n:]


def test_no_make_in_any_builder() -> None:
    builders = [
        c.make_args("down", "x"),
        c.make_args("upload", "x", "UPLOADS=a,b"),
        c.make_args("instance.delete", "x"),
        c.make_args("instance.provision", "x"),
        c.make_args("status", "x"),
        c.package_make_args("package.install", "x", "p"),
        c.package_make_args("package.select", "x", "p"),
        c.package_action_args("x", "p", "a"),
        c.bundle_make_args("bundle.select", "x", "b"),
        c.create_instance_args("n", {"machine": "m", "os": "o", "location": "l"}, "", "", "", ""),
    ]
    for argv in builders:
        assert argv[0] != "make"
        assert argv[0].startswith(str(SCRIPTS))


def test_instance_run_verbs() -> None:
    for verb in ("up", "down", "start", "stop", "ssh", "logs", "provision", "reboot", "ip"):
        assert c.make_args(verb, "inst") == [str(SCRIPTS / "instance-run"), verb, "inst"]


def test_upload_splits_uploads_var() -> None:
    assert c.make_args("upload", "inst", "UPLOADS=a,b") == [
        str(SCRIPTS / "instance-run"), "upload", "inst", "a", "b",
    ]
    assert c.make_args("upload", "inst") == [str(SCRIPTS / "instance-run"), "upload", "inst"]


def test_instance_dedicated_scripts() -> None:
    assert c.make_args("instance.delete", "i") == [str(SCRIPTS / "instance-delete"), "--instance", "i"]
    assert c.make_args("instance.provision", "i") == [str(SCRIPTS / "instance-provision"), "--instance", "i"]
    assert c.make_args("status", "i") == [str(SCRIPTS / "instance-status"), "--instance", "i"]


def test_package_dispatch_and_selection() -> None:
    assert c.package_make_args("package.install", "i", "p") == [
        str(SCRIPTS / "package-dispatch"), "--instance", "i", "--package", "p", "--command", "install",
    ]
    assert _tail(c.package_make_args("package.reinstall", "i", "p", "YES=1"), 3) == [
        "--command", "reinstall", "--yes",
    ]
    assert c.package_make_args("package.uninstall", "i", "p", "YES=1")[-1] == "--yes"
    # without YES=1, no --yes
    assert "--yes" not in c.package_make_args("package.install", "i", "p")
    assert c.package_make_args("package.select", "i", "p") == [
        str(SCRIPTS / "package-selection"), "--instance", "i", "--package", "p", "--add",
    ]
    assert c.package_make_args("package.unselect", "i", "p")[-1] == "--remove"


def test_package_action_and_bundle() -> None:
    assert c.package_action_args("i", "p", "act") == [
        str(SCRIPTS / "package-action"), "--instance", "i", "--package", "p", "--action", "act",
    ]
    assert c.bundle_make_args("bundle.select", "i", "b") == [
        str(SCRIPTS / "bundle-selection"), "--instance", "i", "--bundle", "b", "--add",
    ]
    assert c.bundle_make_args("bundle.unselect", "i", "b")[-1] == "--remove"


def test_create_instance_args_flags() -> None:
    argv = c.create_instance_args(
        "myvm",
        {"machine": "m", "os": "o", "init": "ssh-cloud-init", "location": "l"},
        "dev-ai", "vscode", "50", "8192", "1.2.3.4",
    )
    assert argv[:3] == [str(SCRIPTS / "instance-create"), "--instance", "myvm"]
    # init must be passed — otherwise the created instance fails up/down schema
    # validation ('init' is a required property).
    assert argv[argv.index("--init") + 1] == "ssh-cloud-init"
    assert "--machine" in argv and "--bundles" in argv and "--disk-gb" in argv and "--provider-ip" in argv
    # empty optionals are omitted
    argv2 = c.create_instance_args("m2", {"machine": "m", "os": "o", "location": "l"}, "", "", "", "")
    assert "--bundles" not in argv2 and "--disk-gb" not in argv2
