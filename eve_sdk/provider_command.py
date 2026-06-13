from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from eve_sdk.dispatch import DispatchError, exec_cmd, read_resolved_from_env_or_stdin
from eve_sdk.schema import validate_input, validate_output
from eve_sdk.workdir import Workdir


def emit_dry_run(provider: str, command: str, resolved: dict) -> int:
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
