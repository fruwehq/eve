from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from eve_sdk import state_machine
from eve_sdk.schema import validate_schema
from eve_sdk.workdir import Workdir


class StateError(Exception):
    pass


class State:
    OPERATION_STATUSES: ClassVar[set[str]] = {"running", "succeeded", "failed", "skipped"}
    DESIRED_STATES: ClassVar[set[str]] = {"unknown", "running", "stopped", "absent"}
    PROVIDER_STATES: ClassVar[set[str]] = {
        "unknown",
        "initializing",
        "initialized",
        "planned",
        "changing",
        "running",
        "stopped",
        "absent",
        "error",
    }
    PROVISION_STATES: ClassVar[set[str]] = {"unknown", "provisioning", "provisioned", "error"}
    PACKAGE_STATES: ClassVar[set[str]] = {"unknown", "installed", "missing", "failed", "removed", "reinstalled"}
    DEFAULT_HISTORY_LIMIT = 50

    @classmethod
    def lock_path(cls, instance_name: str) -> Path:
        return Workdir.state_base() / "instances" / f"{instance_name}.lock"

    @classmethod
    @contextmanager
    def _lock(cls, instance_name: str, exclusive: bool) -> Any:
        path = cls.lock_path(instance_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            os.chmod(path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @classmethod
    def read(cls, instance_name: str) -> dict[str, Any]:
        path = Workdir.state_path(instance_name)
        try:
            with cls._lock(instance_name, exclusive=False):
                stored = cls._load_json(path)
                state = cls.default_state(instance_name) | stored
                state.setdefault("package_state", {})
                state.setdefault("observed_state", {})
                state.setdefault("operation_history", [])
                cls.validate_state(state)
                return state
        except json.JSONDecodeError as error:
            raise StateError(f"Cannot parse state for {instance_name}: {error}") from error

    @staticmethod
    def validate_state(state: dict[str, Any]) -> None:
        validate_schema("observed-state.schema.json", state, "Observed state")

    @classmethod
    def write(cls, instance_name: str, state: dict[str, Any]) -> dict[str, Any]:
        path = Workdir.state_path(instance_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with cls._lock(instance_name, exclusive=True):
            cls.validate_state(state)
            cls._atomic_write(path, state)
        return state

    @classmethod
    def modify(cls, instance_name: str, callback: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        path = Workdir.state_path(instance_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with cls._lock(instance_name, exclusive=True):
                state = cls.default_state(instance_name) | cls._load_json(path)
                state.setdefault("package_state", {})
                state.setdefault("observed_state", {})
                state.setdefault("operation_history", [])
                updated = callback(state)
                cls.validate_state(updated)
                cls._atomic_write(path, updated)
                return updated
        except json.JSONDecodeError as error:
            raise StateError(f"Cannot parse state for {instance_name}: {error}") from error

    @staticmethod
    def default_state(instance_name: str, now: str | None = None) -> dict[str, Any]:
        state: dict[str, Any] = {
            "instance": instance_name,
            "desired_state": "unknown",
            "provider_state": "unknown",
            "provision_state": "unknown",
            "package_state": {},
            "observed_state": {},
            "operation_history": [],
            "last_operation": None,
            "last_error": None,
        }
        if now:
            state["created_at"] = now
            state["updated_at"] = now
        return state

    @classmethod
    def record_operation(
        cls,
        instance_name: str,
        operation: str,
        status: str,
        *,
        error: str | None = None,
        desired_state: str | None = None,
        provider_state: str | None = None,
        provision_state: str | None = None,
        package: str | None = None,
        package_state: str | None = None,
    ) -> dict[str, Any]:
        cls._validate_enum(status, cls.OPERATION_STATUSES, "status")
        if desired_state:
            cls._validate_enum(desired_state, cls.DESIRED_STATES, "desired_state")
        if provider_state:
            cls._validate_enum(provider_state, cls.PROVIDER_STATES, "provider_state")
        if provision_state:
            cls._validate_enum(provision_state, cls.PROVISION_STATES, "provision_state")
        if package_state:
            cls._validate_enum(package_state, cls.PACKAGE_STATES, "package_state")

        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        def update(state: dict[str, Any]) -> dict[str, Any]:
            state.setdefault("created_at", now)
            state["updated_at"] = now
            history = state.setdefault("operation_history", [])
            entry = {
                "id": len(history) + 1,
                "name": operation,
                "type": operation.split(".", 1)[0],
                "status": status,
                "at": now,
            }
            state["last_operation"] = entry
            history_entry = dict(entry)
            if error is not None:
                history_entry["error"] = error
            history.append(history_entry)
            state["operation_history"] = history[-cls.DEFAULT_HISTORY_LIMIT :]
            state["last_error"] = error
            if desired_state:
                state["desired_state"] = desired_state
            if provider_state:
                state["provider_state"] = provider_state
            if provision_state:
                state["provision_state"] = provision_state
            if package and package_state:
                state.setdefault("package_state", {})[package] = {"status": package_state, "updated_at": now}
            return state

        return cls.modify(instance_name, update)

    @classmethod
    def update_observed(cls, instance_name: str, observed: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        def update(state: dict[str, Any]) -> dict[str, Any]:
            state["observed_state"] = state.get("observed_state", {}) | observed
            state["updated_at"] = now
            return state

        return cls.modify(instance_name, update)

    @classmethod
    def recover_running(cls, instance_name: str) -> dict[str, Any]:
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        def update(state: dict[str, Any]) -> dict[str, Any]:
            last_op = state.get("last_operation")
            if isinstance(last_op, dict) and last_op.get("status") == "running":
                message = f"Recovered interrupted operation {last_op.get('name', 'unknown')}"
                recovered = last_op | {"status": "failed", "error": message}
                state["last_operation"] = recovered
                state["last_error"] = message
                state["updated_at"] = now
                state["operation_history"] = [
                    entry | {"status": "failed", "error": message}
                    if isinstance(entry, dict) and entry.get("id") == recovered.get("id")
                    else entry
                    for entry in state.get("operation_history", [])
                ]
                if recovered.get("type") == "provider" and recovered.get("name") not in {
                    "provider.resolve",
                    "provider.status",
                    "provider.ip",
                    "provider.ssh",
                }:
                    state["provider_state"] = "error"
                if recovered.get("type") == "provision":
                    state["provision_state"] = "error"
            return state

        return cls.modify(instance_name, update)

    @classmethod
    def build_view(
        cls,
        *,
        instance_name: str,
        resolved: dict[str, Any],
        packages: list[dict[str, Any]],
        paths: dict[str, str],
    ) -> dict[str, Any]:
        state = cls.read(instance_name)
        observed = state.get("observed_state", {})
        reconciled = state_machine.status_with_observed_state(
            {"state": state, "observed_state": observed},
            {"observed_state": observed},
        )["state"]
        package_state = state.get("package_state", {})
        enriched = [pkg | {"state": package_state.get(pkg["id"], {"status": "unknown"})} for pkg in packages]
        selected = [pkg for pkg in enriched if pkg.get("selected")]
        summary = {key: 0 for key in sorted(cls.PACKAGE_STATES)}
        for package_info in selected:
            status = package_info.get("state", {}).get("status", "unknown")
            summary[status] = summary.get(status, 0) + 1
        eps = state_machine.effective_provider_state(reconciled)
        actions_available = state_machine.provider_actions_available(reconciled)
        reconciled["effective_provider_state"] = eps
        reconciled["provider_actions_available"] = actions_available
        return {
            "instance": {
                "name": instance_name,
                "provider": resolved.get("machine", {}).get("provider"),
                "provider_plugin": resolved.get("provider_plugin"),
                "engine": resolved.get("engine"),
                "machine": resolved.get("composition", {}).get("machine"),
                "os": resolved.get("os", {}).get("id"),
                "os_family": resolved.get("os", {}).get("family"),
                "location": resolved.get("location", {}).get("name"),
                "bundles": resolved.get("composition", {}).get("bundles") or [],
                "access": resolved.get("access", {}),
            },
            "state": reconciled,
            "observed_state": reconciled.get("observed_state", {}),
            "effective_provider_state": eps,
            "provider_actions_available": actions_available,
            "packages": {"summary": dict(sorted(summary.items())), "selected": selected, "all": enriched},
            "paths": paths,
        }

    @classmethod
    def delete(cls, instance_name: str) -> None:
        path = Workdir.state_path(instance_name)
        with cls._lock(instance_name, exclusive=True):
            if path.exists():
                path.unlink()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        raw = path.read_text(encoding="utf-8")
        if not raw:
            return {}
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise StateError(f"{path}: expected a JSON object")
        return loaded

    @staticmethod
    def _atomic_write(path: Path, state: dict[str, Any]) -> None:
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.tmp.",
                delete=False,
            ) as tmp:
                tmp_name = tmp.name
                json.dump(state, tmp, indent=2)
                tmp.write("\n")
            os.replace(tmp_name, path)
        except Exception:
            if tmp_name and Path(tmp_name).exists():
                Path(tmp_name).unlink()
            raise

    @staticmethod
    def _validate_enum(value: str, allowed: set[str], label: str) -> None:
        if value not in allowed:
            raise ValueError(f"{label} must be one of: {', '.join(sorted(allowed))}")
