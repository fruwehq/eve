"""Phase 4: the ``eve <group> <verb>`` CLI tree (``scripts/eve-cli``).

Two test layers, mirroring ``test_remote_launchers``:
1. subprocess-driven help/usage checks — assert ``eve --help`` and each
   ``eve <group> --help`` exit 0 and surface their verbs, and that missing a
   required argument prints a clean message and exits 2 (no script is run).
2. command-vector assertions against the pure ``build_command`` translator —
   assert each verb builds the exact underlying script argv (positional
   instance + flag translation) WITHOUT executing it, like the remote_launch
   builders. No instance, cloud, or network is required.
"""

from __future__ import annotations

import argparse
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts" / "eve-cli"

_MODULE = runpy.run_path(str(CLI))
build_command = _MODULE["build_command"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ============================ help / tree shape =========================== #

TOP_LEVEL_GROUPS = [
    "instance", "package", "provider", "bundle", "plugin",
    "catalog", "config", "doctor", "tui", "pull", "batch",
]

# Verbs that must appear in each verb-based group's --help output.
_GROUP_VERBS: dict[str, list[str]] = {
    "instance": [
        "up", "down", "start", "stop", "ssh", "ssh-wait", "ip", "reboot", "logs",
        "info", "env", "validate", "observe", "state", "recover", "view", "paths",
        "provision", "delete", "create", "list", "status", "show-password",
        "provision-wait", "provision-clear",
    ],
    "package": ["list", "select", "unselect", "install", "status", "down",
                "reinstall", "action", "provision", "verify"],
    "provider": ["list", "status", "action"],
    "bundle": ["list", "select", "unselect"],
    "plugin": ["list", "validate", "sync", "test", "source"],
    "catalog": ["list"],
    "config": ["get", "list", "set", "unset"],
}


def test_top_level_help_lists_groups() -> None:
    result = _run("--help")
    assert result.returncode == 0
    for group in TOP_LEVEL_GROUPS:
        assert group in result.stdout


@pytest.mark.parametrize("group", list(_GROUP_VERBS))
def test_group_help_lists_verbs(group: str) -> None:
    result = _run(group, "--help")
    assert result.returncode == 0
    for verb in _GROUP_VERBS[group]:
        assert verb in result.stdout, f"{group} --help missing verb {verb!r}"


@pytest.mark.parametrize("group", ["doctor", "tui", "pull", "batch"])
def test_single_action_group_help_exits_zero(group: str) -> None:
    # These groups take no <verb>; --help must still succeed.
    assert _run(group, "--help").returncode == 0


# ============================ missing-arg exit 2 ========================== #

@pytest.mark.parametrize(
    "args, needle",
    [
        (["instance", "up"], "the following arguments are required: instance"),
        (["package", "install", "mock-dev-a"], "the following arguments are required: --package"),
        (["package", "action", "mock-dev-a", "--package", "mock-app"], "required: --action"),
        (["provider", "action", "--action", "login"], "--provider <id> or INSTANCE"),
    ],
)
def test_missing_required_arg_exits_2(args: list[str], needle: str) -> None:
    result = _run(*args)
    assert result.returncode == 2
    assert needle in result.stderr


# ============================ command-vector (pure) ======================= #
# build_command is pure: it returns the underlying argv relative to the repo
# root without executing anything. Assert it matches the underlying script invocation
# for each verb, covering positional instance + flag translation.

def test_instance_run_verbs_route_through_instance_run() -> None:
    # up/down/start/stop/ssh/ip/reboot/logs/info/env/validate/show-password
    # all map to: scripts/instance-run <target> <instance>
    assert build_command(_ns(group="instance", verb="up", instance="mock-dev-a")) == [
        "scripts/instance-run", "up", "mock-dev-a",
    ]
    assert build_command(_ns(group="instance", verb="ssh-wait", instance="mock-dev-a")) == [
        "scripts/instance-run", "ssh.wait", "mock-dev-a",
    ]
    assert build_command(_ns(group="instance", verb="provision-clear", instance="x")) == [
        "scripts/instance-run", "provision.clear-state", "x",
    ]


def test_instance_status_translates_json_flag() -> None:
    assert build_command(_ns(group="instance", verb="status", instance="mock-dev-a", json=False)) == [
        "scripts/instance-status", "--instance", "mock-dev-a",
    ]
    assert build_command(_ns(group="instance", verb="status", instance="mock-dev-a", json=True)) == [
        "scripts/instance-status", "--instance", "mock-dev-a", "--json",
    ]


def test_instance_create_translates_optional_flags() -> None:
    cmd = build_command(_ns(
        group="instance", verb="create", instance="mock-dev-a",
        machine="mock-small", os="mockos-1.0-arm64", location="home",
        provider_host=None, provider_ip=None, bundles="a,b", packages=None,
        disk_gb=40, memory_mb=None, cpu_cores=None, vcpus=None,
        instance_type=None, root_volume_type=None, plan=None,
    ))
    assert cmd == [
        "scripts/instance-create", "--instance", "mock-dev-a",
        "--machine", "mock-small",
        "--os", "mockos-1.0-arm64",
        "--location", "home",
        "--bundles", "a,b",
        "--disk-gb", "40",
    ]


def test_instance_observe_and_paths_optional_flags() -> None:
    assert build_command(_ns(group="instance", verb="observe", instance="d", ttl=None)) == [
        "scripts/instance-observe", "--instance", "d",
    ]
    assert build_command(_ns(group="instance", verb="observe", instance="d", ttl=60)) == [
        "scripts/instance-observe", "--instance", "d", "--ttl", "60",
    ]
    assert build_command(_ns(group="instance", verb="paths", instance="d", emit=None)) == [
        "scripts/instance-paths", "--instance", "d",
    ]
    assert build_command(_ns(group="instance", verb="paths", instance="d", emit="json")) == [
        "scripts/instance-paths", "--instance", "d", "--emit", "json",
    ]


def test_instance_provision_and_delete_bool_flags() -> None:
    assert build_command(_ns(group="instance", verb="provision", instance="d", force=True)) == [
        "scripts/instance-provision", "--instance", "d", "--force",
    ]
    assert build_command(_ns(group="instance", verb="delete", instance="d",
                             purge=False, force=False)) == [
        "scripts/instance-delete", "--instance", "d",
    ]
    assert build_command(_ns(group="instance", verb="delete", instance="d",
                             purge=True, force=True)) == [
        "scripts/instance-delete", "--instance", "d", "--purge", "--force",
    ]


def test_instance_state_view_recover_list_direct_scripts() -> None:
    assert build_command(_ns(group="instance", verb="state", instance="d")) == [
        "scripts/instance-state", "--instance", "d", "--get",
    ]
    assert build_command(_ns(group="instance", verb="recover", instance="d")) == [
        "scripts/instance-state", "--instance", "d", "--recover-running",
    ]
    assert build_command(_ns(group="instance", verb="view", instance="d")) == [
        "scripts/instance-view", "--instance", "d",
    ]
    assert build_command(_ns(group="instance", verb="list", json=False)) == [
        "scripts/instance-list",
    ]
    assert build_command(_ns(group="instance", verb="list", json=True)) == [
        "scripts/instance-list", "--json",
    ]


def test_package_dispatch_commands() -> None:
    assert build_command(_ns(group="package", verb="install", instance="d", package="mock-app")) == [
        "scripts/package-dispatch", "--instance", "d", "--package", "mock-app",
        "--command", "install",
    ]
    assert build_command(_ns(group="package", verb="status", instance="d", package="mock-app")) == [
        "scripts/package-dispatch", "--instance", "d", "--package", "mock-app",
        "--command", "status",
    ]
    # down/reinstall carry --yes when present.
    assert build_command(_ns(group="package", verb="down", instance="d",
                             package="mock-app", yes=True)) == [
        "scripts/package-dispatch", "--instance", "d", "--package", "mock-app",
        "--command", "down", "--yes",
    ]
    assert build_command(_ns(group="package", verb="reinstall", instance="d",
                             package="mock-app", yes=False)) == [
        "scripts/package-dispatch", "--instance", "d", "--package", "mock-app",
        "--command", "reinstall",
    ]


def test_package_select_unselect_action_verify() -> None:
    assert build_command(_ns(group="package", verb="select", instance="d", package="mock-app")) == [
        "scripts/package-selection", "--instance", "d", "--package", "mock-app", "--add",
    ]
    assert build_command(_ns(group="package", verb="unselect", instance="d", package="mock-app")) == [
        "scripts/package-selection", "--instance", "d", "--package", "mock-app", "--remove",
    ]
    assert build_command(_ns(group="package", verb="action", instance="d",
                             package="rustdesk", action="rustdesk-info")) == [
        "scripts/package-action", "--instance", "d", "--package", "rustdesk",
        "--action", "rustdesk-info",
    ]
    # verify: --package optional.
    assert build_command(_ns(group="package", verb="verify", instance="d", package=None)) == [
        "scripts/package-verify", "--instance", "d",
    ]
    assert build_command(_ns(group="package", verb="verify", instance="d", package="mock-app")) == [
        "scripts/package-verify", "--instance", "d", "--package", "mock-app",
    ]


def test_package_provision_alias_routes_to_instance_provision() -> None:
    assert build_command(_ns(group="package", verb="provision", instance="d", force=True)) == [
        "scripts/instance-provision", "--instance", "d", "--force",
    ]


def test_provider_list_status_action() -> None:
    assert build_command(_ns(group="provider", verb="list", json=False)) == [
        "scripts/plugin-list", "--kind", "provider",
    ]
    assert build_command(_ns(group="provider", verb="status", instance="d")) == [
        "scripts/provider-dispatch", "--instance", "d", "--command", "status",
    ]
    # provider-level action (no instance).
    assert build_command(_ns(group="provider", verb="action", instance=None,
                             provider="mock-cloud", action="login")) == [
        "scripts/provider-dispatch", "--provider", "mock-cloud", "--command", "login",
    ]
    # instance-level action (no --provider).
    assert build_command(_ns(group="provider", verb="action", instance="d",
                             provider=None, action="status")) == [
        "scripts/provider-dispatch", "--instance", "d", "--command", "status",
    ]


def test_provider_action_rejects_both_or_neither() -> None:
    with pytest.raises(SystemExit) as both:
        build_command(_ns(group="provider", verb="action", instance="d",
                          provider="mock-cloud", action="login"))
    assert both.value.code == 2
    with pytest.raises(SystemExit) as neither:
        build_command(_ns(group="provider", verb="action", instance=None,
                          provider=None, action="login"))
    assert neither.value.code == 2


def test_bundle_select_unselect_and_list() -> None:
    assert build_command(_ns(group="bundle", verb="select", instance="d", bundle="desktop")) == [
        "scripts/bundle-selection", "--instance", "d", "--bundle", "desktop", "--add",
    ]
    assert build_command(_ns(group="bundle", verb="unselect", instance="d", bundle="desktop")) == [
        "scripts/bundle-selection", "--instance", "d", "--bundle", "desktop", "--remove",
    ]
    assert build_command(_ns(group="bundle", verb="list", json=False)) == [
        "scripts/catalog-options",
    ]


def test_plugin_list_validate_sync_test() -> None:
    assert build_command(_ns(group="plugin", verb="list", kind=None, json=False)) == [
        "scripts/plugin-list",
    ]
    assert build_command(_ns(group="plugin", verb="list", kind="provider", json=True)) == [
        "scripts/plugin-list", "--kind", "provider", "--json",
    ]
    assert build_command(_ns(group="plugin", verb="validate")) == [
        "scripts/plugin-list", "--validate",
    ]
    assert build_command(_ns(group="plugin", verb="sync")) == ["scripts/plugins-sync"]
    assert build_command(_ns(group="plugin", verb="test",
                             plugin_path="plugins/providers/aws", json=True)) == [
        "scripts/plugin-test", "plugins/providers/aws", "--json",
    ]


def test_plugin_source_translations() -> None:
    assert build_command(_ns(group="plugin", verb="source", source_action="list", json=True)) == [
        "scripts/plugin-source", "list", "--json",
    ]
    assert build_command(_ns(group="plugin", verb="source", source_action="recommended", json=False)) == [
        "scripts/plugin-source", "recommended",
    ]
    assert build_command(_ns(
        group="plugin", verb="source", source_action="add",
        recommended="eve-providers",
    )) == ["scripts/plugin-source", "add", "--recommended", "eve-providers"]
    assert build_command(_ns(
        group="plugin", verb="source", source_action="add",
        url="https://x/y.git", recommended=None, id="y", ref="v1", subdir=None, auth="none",
    )) == ["scripts/plugin-source", "add", "https://x/y.git", "--id", "y", "--ref", "v1", "--auth", "none"]
    assert build_command(_ns(group="plugin", verb="source", source_action="remove", id="y")) == [
        "scripts/plugin-source", "remove", "y",
    ]


def test_catalog_and_config_groups() -> None:
    assert build_command(_ns(group="catalog", verb="list", json=True)) == [
        "scripts/catalog-options", "--json",
    ]
    assert build_command(_ns(group="config", verb="get")) == ["scripts/config-env", "--json"]
    assert build_command(_ns(group="config", verb="list")) == ["scripts/config-env", "--shell"]
    assert build_command(_ns(group="config", verb="set",
                             section="ui", field="tz", value="UTC")) == [
        "scripts/config-save", "ui", "tz", "UTC",
    ]
    assert build_command(_ns(group="config", verb="set",
                             section="ui", field="tz", value=None)) == [
        "scripts/config-save", "ui", "tz",
    ]
    assert build_command(_ns(group="config", verb="unset", section="ui", field="tz")) == [
        "scripts/config-save", "--unset", "ui", "tz",
    ]


def test_doctor_pull_tui_single_action_groups() -> None:
    assert build_command(_ns(group="doctor", json=True)) == ["scripts/doctor", "--json"]
    assert build_command(_ns(group="doctor", json=False)) == ["scripts/doctor"]
    assert build_command(_ns(group="pull", frozen=True, if_stale=300)) == [
        "scripts/plugins-pull", "--frozen", "--if-stale", "300",
    ]
    assert build_command(_ns(group="pull", frozen=False, if_stale=None)) == [
        "scripts/plugins-pull",
    ]
    assert build_command(_ns(group="tui")) == ["scripts/eve-tui"]
