"""Shared helpers for the package-* dispatcher scripts.

Consolidates the pieces that the original bash/sh scripts duplicated verbatim:
the CLIXML/Objs detail scrubber, the status-probe status extraction, the
optional profile-resolve + human-user resolution, the Linux human-run context
builder, and jq-default-compatible JSON emission.

Phase 5 also exposes ``dispatch_package``: the in-process orchestration the
``scripts/package-dispatch`` cold entrypoint and the warm Engine both call.
With a pre-parsed plugin set + catalog (the Engine's memo), the dispatch
resolves and looks up plugins without re-parsing per op.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eve_sdk.dispatch import (
    DispatchError,
    command_vector,
    package_status_from_output,
    prepare_overlay,
    record_package_state,
    stream_command,
    validate_package_support,
)
from eve_sdk.plugin_manifest import PluginManifest
from eve_sdk.resolve import resolve_instance
from eve_sdk.schema import SchemaValidationError, validate_input

# Characters allowed for a unix user name: letters, digits, dot, underscore,
# hyphen. Matches the bash ``case "$human_user" in *[!a-zA-Z0-9._-]*)`` guard.
_HUMAN_USER_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def emit_json(obj: object) -> None:
    """Print ``obj`` as JSON matching jq's default pretty-printed output.

    jq's default format is 2-space indent, keys in insertion order, UTF-8
    passthrough, with a trailing newline. ``json.dumps(indent=2,
    ensure_ascii=False)`` matches byte-for-byte.
    """
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def clean_clixml_details(output: str) -> str:
    """Strip ``\\r`` and CLIXML/<Objs> wrapper noise from captured SSH output.

    Mirrors the bash ``clean_details`` awk: remove all carriage returns, then
    drop lines that are CLIXML preamble, ``<Objs``/``<Obj`` elements,
    ``</Objs>``, or contain ``_x000D__``. The caller strips trailing newlines
    (as bash ``$(...)`` does).
    """
    stripped = output.replace("\r", "")
    lines: list[str] = []
    for line in stripped.split("\n"):
        if line.startswith("#< CLIXML"):
            continue
        if line.startswith("<Objs "):
            continue
        if line.startswith("<Obj "):
            continue
        if line.startswith("</Objs>"):
            continue
        if "_x000D__" in line:
            continue
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


def first_status(details: str, valid: set[str]) -> str:
    """Return the first line of ``details`` that is exactly a status keyword.

    Mirrors ``awk '/^(...)$/ {print; exit}'``. Returns ``""`` if no line
    matches.
    """
    for line in details.split("\n"):
        if line in valid:
            return line
    return ""


def optional_profile_env(root: Path, profile: str) -> dict[str, str] | None:
    """Resolve a profile via ``scripts/profile-resolve`` returning ``None`` on failure.

    Mirrors the bash ``if resolved_env=$(... 2>/dev/null); then ... else ... fi``
    pattern: stderr is suppressed (not propagated), and a non-zero exit returns
    ``None`` rather than raising.
    """
    result = subprocess.run(
        [str(root / "scripts/profile-resolve"), "--profile", profile, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return None
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def resolve_human_user(root: Path, profile: str, script_name: str) -> str:
    """Resolve the human user name for a profile.

    Mirrors the bash sequence: try profile-resolve (failure is OK), take
    ``VM_USER_NAME`` then ``SSH_USER``, fall back to ``id -un``, and validate
    the charset. Exits 2 with the original ``<script_name>: unsupported VM user
    name`` message on an invalid name.
    """
    resolved = optional_profile_env(root, profile)
    vm_user = ""
    ssh_user = ""
    if resolved is not None:
        vm_user = resolved.get("VM_USER_NAME", "")
        ssh_user = resolved.get("SSH_USER", "")
    human_user = vm_user or ssh_user
    if not human_user:
        human_user = subprocess.check_output(["id", "-un"], text=True).strip()
    if not _HUMAN_USER_RE.match(human_user):
        print(f"{script_name}: unsupported VM user name: {human_user}", file=sys.stderr)
        raise SystemExit(2)
    return human_user


def build_linux_human_context(human_user: str, remote_command: str, include_cargo: bool) -> str:
    """Build the remote bash wrapper that exports the human user's environment.

    Mirrors the unquoted heredoc in package-status-command / package-down-command:
    only ``$HUMAN_USER`` and ``$REMOTE_COMMAND`` are expanded; every ``\\$``
    becomes a literal ``$``. When ``include_cargo`` is True the PATH includes
    ``.cargo/bin`` (package-status-command); otherwise it does not
    (package-down-command).
    """
    cargo = ":$EVE_HUMAN_HOME/.cargo/bin" if include_cargo else ""
    template = (
        "set -eu\n"
        'EVE_HUMAN_USER="{h}"\n'
        'EVE_HUMAN_HOME=$(getent passwd "$EVE_HUMAN_USER" | cut -d: -f6)\n'
        'EVE_HUMAN_UID=$(id -u "$EVE_HUMAN_USER")\n'
        "export EVE_HUMAN_USER EVE_HUMAN_HOME EVE_HUMAN_UID\n"
        'export HOME="$EVE_HUMAN_HOME"\n'
        'export PATH="$EVE_HUMAN_HOME/.local/bin{cargo}:$PATH"\n'
        "eve_human_run() {{\n"
        '  sudo -H -u "$EVE_HUMAN_USER" env \\\n'
        '    HOME="$EVE_HUMAN_HOME" \\\n'
        '    USER="$EVE_HUMAN_USER" \\\n'
        '    LOGNAME="$EVE_HUMAN_USER" \\\n'
        '    PATH="$EVE_HUMAN_HOME/.local/bin{cargo}:$PATH" \\\n'
        '    XDG_RUNTIME_DIR="/run/user/$EVE_HUMAN_UID" \\\n'
        '    "$@"\n'
        "}}\n"
        "{cmd}"
    )
    return template.format(h=human_user, cargo=cargo, cmd=remote_command)


def run_status_probe(
    ssh_helper: str,
    profile: str,
    remote_command: str,
) -> tuple[int, str]:
    """Run a status probe via ``ssh_helper`` and return (exit_status, details).

    Mirrors the bash ``set +e; output="$(... 2>&1); exit_status=$?; set -e``
    capture: stdout and stderr are merged, trailing newlines are stripped
    (command-substitution semantics), and CLIXML noise is scrubbed.
    """
    result = subprocess.run(
        [ssh_helper, profile, "--", remote_command],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )
    output = result.stdout.rstrip("\n")
    details = clean_clixml_details(output)
    return result.returncode, details


def quote_ps_single(value: str) -> str:
    """Single-quote a string for PowerShell (double internal quotes).

    Mirrors the bash ``quote_ps_string`` helper.
    """
    return "'" + value.replace("'", "''") + "'"


def encode_ps_command(script: str) -> str:
    """Encode a PowerShell script as a ``-EncodedCommand`` argument.

    Mirrors ``iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\\n'``.
    """
    import base64
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


# --------------------------------------------------------------------------- #
# In-process dispatch orchestration (Phase 5)
# --------------------------------------------------------------------------- #

def _run_plugin(
    plugin: dict[str, Any],
    command: str,
    resolved: dict[str, Any],
    dry_run: bool,
    on_output: Callable[[str], None] | None = None,
) -> str:
    commands = plugin.get("commands")
    if not isinstance(commands, dict):
        raise DispatchError(f"package plugin {plugin['id']} has no commands")
    spec = commands.get(command)
    if not isinstance(spec, dict):
        raise DispatchError(f"package plugin {plugin['id']} has no command: {command}")

    # For a merged dual-OS package, select the half matching the instance OS so the
    # command-hook/provision resolution finds commands/<os>/ in the right repo.
    os_obj = resolved.get("os")
    os_family = str(os_obj.get("family", "")) if isinstance(os_obj, dict) else ""
    os_paths_raw = plugin.get("os_paths")
    os_paths = os_paths_raw if isinstance(os_paths_raw, dict) else {}
    manifest_path = os_paths.get(os_family) or plugin["path"]
    env = os.environ | {
        "EVE_INSTANCE_NAME": resolved["instance"]["name"],
        "EVE_PACKAGE_PLUGIN": str(plugin["id"]),
        "EVE_PACKAGE_PLUGIN_ROOT": str(Path(str(manifest_path)).parent),
        "EVE_RESOLVED_JSON": json.dumps(resolved, separators=(",", ":")),
    }
    if dry_run:
        env["EVE_PLUGIN_DRY_RUN"] = "1"

    status, output = stream_command(
        command_vector(plugin, spec),
        env=env,
        stdin_text=json.dumps(resolved, separators=(",", ":")),
        on_output=on_output,
    )
    if status != 0:
        raise DispatchError(f"package command failed: {command}")
    return output


def dispatch_package(
    instance_name: str,
    package_id: str,
    command: str,
    *,
    registry_path: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    plugins: list[dict[str, Any]] | None = None,
    catalog: dict[str, list[dict[str, Any]]] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> int:
    """Run a package command end-to-end and return its exit code (0 on success).

    The single orchestration entry both ``scripts/package-dispatch`` (cold) and
    ``Engine.package`` (warm) call. ``plugins`` / ``catalog`` are the warm
    memo; when ``None`` they are loaded from disk (cold behavior, byte-identical).
    """
    resolved = resolve_instance(instance_name, registry_path, catalog=catalog, plugins=plugins)
    try:
        validate_input(resolved)
    except SchemaValidationError as error:
        print(f"package-dispatch: {error}", file=sys.stderr)
        return 1

    try:
        # Look up via the parsed set when provided (warm), else fall back to the
        # cold path (subprocess to plugin-list). The single-OS/dual-OS merge in
        # PluginManifest.load_all is preserved when going through the cold path.
        if plugins is None:
            plugin = _load_public_plugin("package", package_id)
        else:
            plugin = _select_plugin(plugins, "package", package_id)
        validate_package_support(package_id, plugin, resolved)

        destructive = bool(plugin.get("down", {}).get("destructive")) if isinstance(plugin.get("down"), dict) else False
        destructive_confirmed = yes or os.environ.get("EVE_CONFIRM_DESTRUCTIVE") == "1"
        if command in {"down", "reinstall"} and destructive and not destructive_confirmed:
            raise DispatchError(
                f"package {package_id} down is destructive; "
                "pass --yes or EVE_CONFIRM_DESTRUCTIVE=1"
            )

        overlay = prepare_overlay(instance_name, registry_path)
        os.environ["EVE_CATALOG_LOCAL"] = overlay
        if registry_path:
            os.environ["EVE_INSTANCE_REGISTRY"] = registry_path

        # Record "running" only after lookup/validation/overlay prep succeeded —
        # so a missing-package or unsupported-version failure records only the
        # "failed" entry (matching the cold script's behavior).
        if not dry_run:
            record_package_state(instance_name, command, "running", package_id)

        if command == "reinstall" and "reinstall" not in plugin.get("commands", {}):
            _run_plugin(plugin, "down", resolved, dry_run, on_output)
            output = _run_plugin(plugin, "install", resolved, dry_run, on_output)
        else:
            output = _run_plugin(plugin, command, resolved, dry_run, on_output)
    except Exception as error:
        if not dry_run:
            try:
                record_package_state(
                    instance_name, command, "failed", package_id, "failed", str(error)
                )
            except Exception as state_error:
                print(f"package-dispatch: failed to record failure state: {state_error}", file=sys.stderr)
        print(f"package-dispatch: {error}", file=sys.stderr)
        return 1

    package_state = {
        "install": "installed",
        "down": "removed",
        "reinstall": "reinstalled",
    }.get(command)
    if package_state is None:
        package_state = package_status_from_output(output) or "unknown"
    if not dry_run:
        record_package_state(instance_name, command, "succeeded", package_id, package_state)
    return 0


def _select_plugin(plugins: list[dict[str, Any]], kind: str, plugin_id: str) -> dict[str, Any]:
    """Look up a plugin in a pre-parsed set (warm path)."""
    for plugin in plugins:
        if (
            isinstance(plugin, dict)
            and plugin.get("kind") == kind
            and plugin.get("id") == plugin_id
        ):
            return plugin
    raise DispatchError(f"{kind} plugin not found: {plugin_id}")


def _load_public_plugin(kind: str, plugin_id: str) -> dict[str, Any]:
    """Cold-path plugin lookup that returns the public projection.

    Mirrors what ``scripts/package-dispatch`` got via ``eve_sdk.dispatch.load_plugin``
    (which subprocesses to ``scripts/plugin-list``, which runs
    ``PluginManifest.public`` on every manifest). Used so the cold and warm
    paths see the same shape (with ``path`` / ``source`` / ``os_paths``).
    """
    for plugin in PluginManifest.load_all(kind):
        if plugin.get("id") == plugin_id:
            return PluginManifest.public(plugin)
    raise DispatchError(f"{kind} plugin not found: {plugin_id}")
