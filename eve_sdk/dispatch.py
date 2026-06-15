from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eve_sdk.schema import validate_output
from eve_sdk.state import State
from eve_sdk.workdir import Workdir

PACKAGE_STATUS_VALUES = {"installed", "missing", "unknown", "failed"}
PROVIDER_INTERACTIVE_COMMANDS = {"ssh"}


class DispatchError(Exception):
    pass


def command_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Env for invoking plugin/script commands. Ensures the eve repo root is on
    PYTHONPATH so external (synced) plugin command scripts can `import eve_sdk`
    regardless of where they live on disk (their own `parents[N]` path assumes
    the in-repo layout and is wrong once extracted)."""
    env = os.environ | (extra or {})
    root = str(Workdir.repo_root())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root + (os.pathsep + existing if existing else "")
    return env


def run_json(*cmd: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        list(cmd),
        cwd=Workdir.repo_root(),
        env=command_env(env),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise DispatchError(result.stdout + result.stderr)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DispatchError(f"invalid JSON from {' '.join(cmd)}: {error}") from error
    if not isinstance(parsed, dict):
        raise DispatchError(f"expected JSON object from {' '.join(cmd)}")
    return parsed


def command_vector(plugin: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    exec_value = str(spec["exec"])
    exec_path = Path(exec_value)
    if not exec_path.is_absolute():
        plugin_exec = Path(str(plugin["path"])).parent / exec_path
        root_exec = Workdir.repo_root() / exec_path
        exec_path = plugin_exec if plugin_exec.exists() else root_exec
    if not exec_path.is_file() or not os.access(exec_path, os.X_OK):
        raise DispatchError(f"plugin {plugin['id']} command is not executable: {spec['exec']}")
    return [str(exec_path), *[str(arg) for arg in spec.get("args", [])]]


def load_plugin(
    kind: str,
    plugin_id: str,
    plugins: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Look up a plugin by ``(kind, id)``.

    With ``plugins`` (a pre-parsed set), filter in-process — the warm Engine
    path. Without it, subprocess to ``scripts/plugin-list`` (the cold path).
    """
    if plugins is not None:
        for plugin in plugins:
            if (
                isinstance(plugin, dict)
                and plugin.get("kind") == kind
                and plugin.get("id") == plugin_id
            ):
                return plugin
        raise DispatchError(f"{kind} plugin not found: {plugin_id}")
    doc = run_json(str(Workdir.repo_root() / "scripts/plugin-list"), "--kind", kind, "--json")
    plugins_list = doc.get("plugins", [])
    if not isinstance(plugins_list, list):
        raise DispatchError("plugin-list returned invalid plugins payload")
    for plugin in plugins_list:
        if isinstance(plugin, dict) and plugin.get("id") == plugin_id:
            return plugin
    raise DispatchError(f"{kind} plugin not found: {plugin_id}")


def resolve_instance(instance_name: str, registry_path: str | None = None) -> dict[str, Any]:
    cmd = [
        str(Workdir.repo_root() / "scripts/instance-resolve"),
        "--instance",
        instance_name,
        "--emit",
        "json",
    ]
    if registry_path:
        cmd.extend(["--registry", registry_path])
    return run_json(*cmd)


def instance_paths(instance_name: str, registry_path: str | None = None) -> dict[str, Any]:
    cmd = [
        str(Workdir.repo_root() / "scripts/instance-paths"),
        "--instance",
        instance_name,
        "--emit",
        "json",
    ]
    if registry_path:
        cmd.extend(["--registry", registry_path])
    return run_json(*cmd)


def prepare_overlay(instance_name: str, registry_path: str | None = None) -> str:
    overlay: str = str(instance_paths(instance_name, registry_path)["INSTANCE_OVERLAY_PATH"])
    Path(overlay).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(Workdir.repo_root() / "scripts/instance-profile-overlay"),
        "--instance",
        instance_name,
        "--output",
        overlay,
    ]
    if registry_path:
        cmd.extend(["--registry", registry_path])
    result = subprocess.run(cmd, cwd=Workdir.repo_root(), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise DispatchError(result.stdout + result.stderr)
    return overlay


def record_provider_state(
    instance_name: str,
    command: str,
    status: str,
    error: str | None = None,
    desired_state: str | None = None,
    provider_state: str | None = None,
) -> None:
    if os.environ.get("EVE_DISABLE_STATE") == "1":
        return
    State.record_operation(
        instance_name,
        f"provider.{command}",
        status,
        error=error,
        desired_state=desired_state,
        provider_state=provider_state,
    )


def record_package_state(
    instance_name: str,
    command: str,
    status: str,
    package_id: str,
    package_state: str | None = None,
    error: str | None = None,
) -> None:
    if os.environ.get("EVE_DISABLE_STATE") == "1":
        return
    State.record_operation(
        instance_name,
        f"package.{command}",
        status,
        package=package_id,
        package_state=package_state,
        error=error,
    )


def desired_state_for(command: str | None) -> str | None:
    return {"up": "running", "start": "running", "stop": "stopped", "down": "absent"}.get(command or "")


def provider_state_for(command: str | None, status: str) -> str | None:
    command = command or ""
    if status == "running" and command in {"up", "down", "start", "stop"}:
        return "changing"
    if status == "failed":
        return None if command in {"resolve", "status", "ip", "ssh"} else "error"
    if status != "succeeded":
        return None
    return {
        "init": "initialized",
        "plan": "planned",
        "up": "running",
        "start": "running",
        "stop": "stopped",
        "down": "absent",
    }.get(command)


def interactive_provider_command(plugin: dict[str, Any], command: str) -> bool:
    if command in PROVIDER_INTERACTIVE_COMMANDS:
        return True
    for action in plugin.get("actions", []):
        if (
            isinstance(action, dict)
            and action.get("interactive") is True
            and action.get("target") == f"provider.{command}"
        ):
            return True
    return False


def last_json_object(output: str, keys: set[str]) -> dict[str, Any] | None:
    for index in range(len(output) - 1, -1, -1):
        if output[index] != "{":
            continue
        try:
            parsed = json.loads(output[index:].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and keys.intersection(parsed):
            return parsed
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and keys.intersection(parsed):
            return parsed
    return None


def validate_provider_output(output: str) -> None:
    parsed = last_json_object(output, {"status", "ip"})
    if parsed is not None:
        validate_output(parsed, "provider_command_output")


def package_status_from_output(output: str) -> str | None:
    parsed = last_json_object(output, {"status"})
    if parsed is None:
        return None
    validate_output(parsed, "package_command_output")
    status = parsed.get("status")
    return status if status in PACKAGE_STATUS_VALUES else None


def support_allowed(supports: dict[str, Any], field: str, value: object) -> bool:
    allowed = supports.get(field) or []
    return not allowed or str(value) in allowed


def validate_package_support(package_id: str, plugin: dict[str, Any], resolved: dict[str, Any]) -> None:
    supports = plugin.get("supports") or {}
    os_doc = resolved["os"]
    os_family = os_doc["family"]
    checks = [
        ("os_families", os_family, "os family"),
        ("arches", os_doc.get("arch", ""), "architecture"),
        ("os_ids", os_doc["id"], "OS"),
        ("os_versions", os_doc.get("version", ""), "OS version"),
        (f"{os_family}_versions", os_doc.get("version", ""), f"{os_family} version"),
    ]
    for field, value, label in checks:
        if not support_allowed(supports, field, value):
            raise DispatchError(f"package plugin {package_id} does not support {label} {value}")
    if (
        os_family == "ubuntu"
        and package_id == "rustdesk"
        and "gnome-desktop" in resolved.get("bundle_packages", [])
    ):
        raise DispatchError(
            "package plugin rustdesk is disabled for gnome-desktop because RustDesk cannot "
            "unattended-capture GNOME/Wayland sessions"
        )


def stream_command(
    cmd: list[str],
    *,
    env: dict[str, str],
    stdin_text: str | None = None,
    capture_stdout: bool = True,
    on_output: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Run ``cmd`` and return ``(exit_code, stdout)``.

    By default the child's stdout/stderr are written through to this
    process's stdout/stderr (legacy behavior). When ``on_output`` is provided,
    output is read line-by-line in real time and each line is passed to the
    callback instead — the streaming hook the warm Engine exposes so a UI can
    render progress without owning the subprocess.
    """
    if on_output is None:
        process = subprocess.Popen(
            cmd,
            cwd=Workdir.repo_root(),
            env=command_env(env),
            text=True,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(stdin_text)
        if stdout:
            sys.stdout.write(stdout)
            sys.stdout.flush()
        if stderr:
            sys.stderr.write(stderr)
            sys.stderr.flush()
        return process.returncode or 0, stdout if capture_stdout else ""

    # Streaming read: merge stderr into stdout, line-buffer to the callback.
    process = subprocess.Popen(
        cmd,
        cwd=Workdir.repo_root(),
        env=command_env(env),
        text=True,
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    if stdin_text is not None:
        assert process.stdin is not None
        process.stdin.write(stdin_text)
        process.stdin.close()
    accumulated: list[str] = []
    assert process.stdout is not None
    while True:
        line = process.stdout.readline()
        if line == "":
            break
        accumulated.append(line)
        on_output(line.rstrip("\n"))
    process.wait()
    return process.returncode or 0, "".join(accumulated) if capture_stdout else ""


def read_resolved_from_env_or_stdin() -> dict[str, Any]:
    raw = os.environ.get("EVE_RESOLVED_JSON")
    if raw is None or raw == "":
        raw = sys.stdin.read()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DispatchError(f"failed to parse resolved JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise DispatchError("resolved JSON must be an object")
    return parsed


def open_url(url: str) -> None:
    system = platform.system()
    if system == "Darwin":
        os.execvp("open", ["open", url])
    if system == "Linux":
        os.execvp("xdg-open", ["xdg-open", url])
    raise DispatchError(f"unsupported OS for opening URLs: {system}")


def exec_cmd(cmd: list[str], env: dict[str, str] | None = None) -> None:
    os.chdir(Workdir.repo_root())
    os.execvpe(cmd[0], cmd, command_env(env))
