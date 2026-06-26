from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eve_sdk.dispatch import (
    DispatchError,
    command_vector,
    desired_state_for,
    exec_cmd,
    interactive_provider_command,
    prepare_overlay,
    provider_state_for,
    read_resolved_from_env_or_stdin,
    record_provider_state,
    stream_command,
    validate_provider_output,
)
from eve_sdk.plugin_manifest import PluginManifest
from eve_sdk.resolve import resolve_instance
from eve_sdk.schema import validate_input, validate_output
from eve_sdk.secrets import Secrets
from eve_sdk.workdir import Workdir


def emit_dry_run(provider: str, command: str, resolved: dict[str, Any]) -> int:
    payload = {
        "kind": "provider",
        "provider": provider,
        "command": command,
        "instance": resolved["instance"]["name"],
        "profile": resolved["instance"]["name"],
        "engine": resolved["engine"],
        "dry_run": os.environ.get("EVE_PLUGIN_DRY_RUN") == "1",
    }
    validate_output(payload, "provider_command_output")
    print(json.dumps(payload, separators=(",", ":")))
    return 0


def _provider_from_executable() -> str:
    path = Path(sys.argv[0]).resolve()
    parts = path.parts
    try:
        index = parts.index("providers")
        return parts[index + 1]
    except (ValueError, IndexError):
        return os.environ.get("EVE_PROVIDER_PLUGIN", "unknown")


def dispatch(argv: list[str]) -> int:
    if not argv:
        print("Usage: provider-command <command>", file=sys.stderr)
        return 2
    command = argv[0]
    extra_args = argv[1:]
    try:
        resolved = read_resolved_from_env_or_stdin()
        validate_input(resolved)
        provider = os.environ.get("EVE_PROVIDER_PLUGIN") or _provider_from_executable()
        resolved_provider = resolved["machine"]["provider"]
        if resolved_provider != provider:
            raise DispatchError(f"provider command for {provider} cannot handle resolved provider {resolved_provider}")

        if os.environ.get("EVE_PLUGIN_DRY_RUN") == "1" or command == "resolve":
            return emit_dry_run(provider, command, resolved)

        engine = resolved["engine"]
        if command == "init":
            if engine == "metal":
                print(f"[{provider}] metal target has no terraform init step", file=sys.stderr)
                return 0
            exec_cmd([str(Workdir.repo_root() / "scripts/tf-init"), resolved["instance"]["name"]])
        if command == "plan":
            if engine == "vagrant":
                exec_cmd([str(Workdir.repo_root() / "scripts/vagrant-up"), "--plan", resolved["instance"]["name"]])
            if engine == "metal":
                print(f"[{provider}] metal target uses direct provisioning; no terraform plan", file=sys.stderr)
                exec_cmd(
                    [
                        str(Workdir.repo_root() / "scripts/profile-resolve"),
                        "--profile",
                        resolved["instance"]["name"],
                        "--emit",
                        "env",
                    ]
                )
            exec_cmd([str(Workdir.repo_root() / "scripts/tf-plan"), resolved["instance"]["name"]])
        if command == "up":
            if engine == "vagrant":
                exec_cmd([str(Workdir.repo_root() / "scripts/vagrant-up"), resolved["instance"]["name"]])
            if engine == "metal":
                print(f"[{provider}] metal target already exists; skipping VM create", file=sys.stderr)
                return 0
            exec_cmd([str(Workdir.repo_root() / "scripts/tf-apply"), resolved["instance"]["name"]])
        if command == "down":
            if engine == "vagrant":
                exec_cmd([str(Workdir.repo_root() / "scripts/vagrant-destroy"), resolved["instance"]["name"]])
            if engine == "metal":
                print(f"[{provider}] metal target lifecycle is persistent; skipping VM delete", file=sys.stderr)
                return 0
            exec_cmd([str(Workdir.repo_root() / "scripts/tf-destroy"), resolved["instance"]["name"]])
        if command in {"start", "stop", "status"}:
            exec_cmd([str(Workdir.repo_root() / f"scripts/{command}"), resolved["instance"]["name"]])
        if command == "ip":
            exec_cmd([str(Workdir.repo_root() / "scripts/instance-ip"), resolved["instance"]["name"]])
        if command == "ssh":
            exec_cmd([str(Workdir.repo_root() / "scripts/instance-ssh"), resolved["instance"]["name"], *extra_args])
        raise DispatchError(f"unsupported provider command: {command}")
    except Exception as error:
        print(f"provider-command: {error}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
# In-process dispatch orchestration (Phase 5)
# --------------------------------------------------------------------------- #

def _inject_secrets(
    provider_name: str, plugin: dict[str, Any], env: dict[str, str]
) -> dict[str, str]:
    secrets = Secrets.read(provider_name)
    if not secrets:
        return env
    schema_secrets = (plugin.get("config_schema") or {}).get("secrets") or {}
    for secret_key, value in secrets.items():
        env[secret_key] = value
        schema_entry = schema_secrets.get(secret_key)
        if isinstance(schema_entry, dict):
            mapped = schema_entry.get("env_var")
            if mapped:
                env[mapped] = value
    return env


def _select_plugin(plugins: list[dict[str, Any]], kind: str, plugin_id: str) -> dict[str, Any]:
    for plugin in plugins:
        if (
            isinstance(plugin, dict)
            and plugin.get("kind") == kind
            and plugin.get("id") == plugin_id
        ):
            return plugin
    raise DispatchError(f"{kind} plugin not found: {plugin_id}")


def _load_public_plugin(kind: str, plugin_id: str) -> dict[str, Any]:
    for plugin in PluginManifest.load_all(kind):
        if plugin.get("id") == plugin_id:
            return PluginManifest.public(plugin)
    raise DispatchError(f"{kind} plugin not found: {plugin_id}")


def dispatch_provider_command(
    provider_name: str,
    command: str,
    *,
    dry_run: bool = False,
    extra_args: tuple[str, ...] | list[str] = (),
    plugins: list[dict[str, Any]] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> int:
    """Provider-level (no instance) command orchestration.

    Used for bootstrap actions like ``login`` that run before any instance
    exists. The same path ``scripts/provider-dispatch`` (cold) and
    ``Engine.provider`` (warm) call.
    """
    plugin = (
        _select_plugin(plugins, "provider", provider_name)
        if plugins is not None
        else _load_public_plugin("provider", provider_name)
    )
    spec = plugin.get("commands", {}).get(command)
    if not isinstance(spec, dict):
        raise DispatchError(f"provider plugin {provider_name} has no command: {command}")
    cmd = command_vector(plugin, spec) + list(extra_args)
    env = _inject_secrets(provider_name, plugin, dict(os.environ) | {"EVE_PROVIDER_PLUGIN": provider_name})
    if dry_run:
        env["EVE_PLUGIN_DRY_RUN"] = "1"
        print(json.dumps({"kind": "provider", "provider": provider_name, "command": command, "dry_run": True}))
        return 0
    # Provider-level commands (login etc.) replace the process: this never returns.
    exec_cmd(cmd, env)
    return 0


def dispatch_instance_command(
    instance_name: str,
    command: str,
    *,
    registry_path: str | None = None,
    dry_run: bool = False,
    extra_args: tuple[str, ...] | list[str] = (),
    plugins: list[dict[str, Any]] | None = None,
    catalog: dict[str, list[dict[str, Any]]] | None = None,
    on_output: Callable[[str], None] | None = None,
) -> int:
    """Instance-scoped provider command orchestration.

    The single path ``scripts/provider-dispatch`` (cold) and ``Engine.provider``
    (warm) call. Resolves + looks up plugins via the warm memo when provided.
    """
    resolved = resolve_instance(instance_name, registry_path, catalog=catalog, plugins=plugins)
    provider = resolved["machine"]["provider"]
    plugin = (
        _select_plugin(plugins, "provider", provider)
        if plugins is not None
        else _load_public_plugin("provider", provider)
    )
    spec = plugin.get("commands", {}).get(command)
    if not isinstance(spec, dict):
        raise DispatchError(f"provider plugin {provider} has no command: {command}")
    cmd = command_vector(plugin, spec) + list(extra_args)

    if dry_run:
        payload = {
            "kind": "provider",
            "provider": provider,
            "command": command,
            "instance": instance_name,
            "profile": instance_name,
            "engine": resolved["engine"],
            "dry_run": True,
        }
        validate_output(payload, "provider_command_output")
        print(json.dumps(payload, separators=(",", ":")))
        return 0

    overlay = prepare_overlay(instance_name, registry_path)
    env = _inject_secrets(provider, plugin, dict(os.environ) | {
        "EVE_CATALOG_LOCAL": overlay,
        "EVE_INSTANCE_NAME": instance_name,
        "EVE_PROVIDER_PLUGIN": provider,
        "EVE_RESOLVED_JSON": json.dumps(resolved, separators=(",", ":")),
    })
    if registry_path:
        env["EVE_INSTANCE_REGISTRY"] = registry_path

    # Merge the overlay/secrets/resolved-env into os.environ so all subsequent
    # exec_cmd calls (tf-init, tf-apply, tf-destroy — which build via
    # command_env() from os.environ) inherit them. Without this, the tf-*
    # scripts don't get EVE_CATALOG_LOCAL and profile-resolve can't find the
    # instance's overlay catalog.
    os.environ.update(env)

    if interactive_provider_command(plugin, command):
        # Interactive commands (ssh etc.) replace the process; never returns.
        exec_cmd(cmd, env)
        return 0

    desired_state = desired_state_for(command)
    record_provider_state(
        instance_name,
        command,
        "running",
        desired_state=desired_state,
        provider_state=provider_state_for(command, "running"),
    )

    exit_status, output = stream_command(
        cmd, env=env, stdin_text=json.dumps(resolved, separators=(",", ":")), on_output=on_output
    )
    if exit_status == 0:
        try:
            validate_provider_output(output)
        except Exception as error:
            record_provider_state(
                instance_name,
                command,
                "failed",
                error=f"invalid provider output: {error}",
                desired_state=desired_state,
                provider_state=provider_state_for(command, "failed"),
            )
            print(f"provider-dispatch: {error}", file=sys.stderr)
            return 1
        record_provider_state(
            instance_name,
            command,
            "succeeded",
            desired_state=desired_state,
            provider_state=provider_state_for(command, "succeeded"),
        )
    else:
        try:
            record_provider_state(
                instance_name,
                command,
                "failed",
                error=f"exit {exit_status}",
                desired_state=desired_state,
                provider_state=provider_state_for(command, "failed"),
            )
        except Exception as error:
            print(f"provider-dispatch: failed to record failure state: {error}", file=sys.stderr)
    return exit_status
