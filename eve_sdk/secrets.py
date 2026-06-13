from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.atomic_yaml import AtomicYaml
from eve_sdk.workdir import Workdir


class SecretsError(Exception):
    pass


class Secrets:
    @staticmethod
    def secrets_dir() -> Path:
        override = os.environ.get("EVE_SECRETS_DIR")
        return Path(os.path.abspath(os.path.expanduser(override))) if override else Workdir.eve_dir() / "secrets"

    @classmethod
    def path_for(cls, provider_id: str) -> Path:
        return cls.secrets_dir() / f"{provider_id}.yaml"

    @classmethod
    def lock_path(cls, provider_id: str) -> Path:
        return cls.secrets_dir() / f"{provider_id}.lock"

    @classmethod
    def ensure_secrets_dir(cls) -> Path:
        return Workdir.ensure_dir(cls.secrets_dir())

    @classmethod
    def read(cls, provider_id: str) -> dict[str, str]:
        path = cls.path_for(provider_id)
        try:
            with AtomicYaml.with_lock(cls.lock_path(provider_id)):
                if not path.exists():
                    return {}
                raw = path.read_text(encoding="utf-8")
                if not raw.strip():
                    return {}
                parsed = yaml.safe_load(raw)
                if not isinstance(parsed, dict) or provider_id not in parsed:
                    raise SecretsError(f"Secrets file {path} must have top-level key '{provider_id}'")
                secrets = parsed[provider_id]
                if not isinstance(secrets, dict):
                    raise SecretsError(f"Secrets file {path}: '{provider_id}' must be a mapping")
                cls._validate_values(provider_id, secrets)
                return {str(key): value for key, value in secrets.items() if value is not None}
        except yaml.YAMLError as error:
            raise SecretsError(f"Cannot parse secrets for {provider_id}: {error}") from error

    @classmethod
    def write(cls, provider_id: str, values: Mapping[str, str | None]) -> dict[str, str | None]:
        cls._validate_values(provider_id, values)
        cls.ensure_secrets_dir()
        path = cls.path_for(provider_id)
        payload = {provider_id: dict(values)}
        with AtomicYaml.with_lock(cls.lock_path(provider_id)):
            AtomicYaml.atomic_write(path, payload)
            os.chmod(path, 0o600)
        return dict(values)

    @classmethod
    def update(cls, provider_id: str, partial: Mapping[str, str | None]) -> dict[str, str]:
        cls.ensure_secrets_dir()
        path = cls.path_for(provider_id)
        with AtomicYaml.with_lock(cls.lock_path(provider_id)):
            current = AtomicYaml.load_yaml(path)
            provider_values = current.setdefault(provider_id, {})
            if not isinstance(provider_values, dict):
                raise SecretsError(f"Secrets file {path}: '{provider_id}' must be a mapping")
            for key, value in partial.items():
                if value is None:
                    provider_values.pop(str(key), None)
                else:
                    provider_values[str(key)] = value
            cls._validate_values(provider_id, provider_values)
            AtomicYaml.atomic_write(path, current)
            os.chmod(path, 0o600)
            return {str(key): value for key, value in provider_values.items() if value is not None}

    @classmethod
    def delete(cls, provider_id: str, keys: str | list[str] | tuple[str, ...] = "all") -> None:
        path = cls.path_for(provider_id)
        if not path.exists():
            return
        with AtomicYaml.with_lock(cls.lock_path(provider_id)):
            if keys == "all":
                if path.exists():
                    path.unlink()
                return
            current = AtomicYaml.load_yaml(path)
            provider_values = current.setdefault(provider_id, {})
            if not isinstance(provider_values, dict):
                raise SecretsError(f"Secrets file {path}: '{provider_id}' must be a mapping")
            for key in keys:
                provider_values.pop(str(key), None)
            if provider_values:
                AtomicYaml.atomic_write(path, current)
                os.chmod(path, 0o600)
            elif path.exists():
                path.unlink()

    @classmethod
    def modify(
        cls,
        provider_id: str,
        callback: Callable[[dict[str, str]], Mapping[str, str | None]],
    ) -> dict[str, str | None]:
        cls.ensure_secrets_dir()
        path = cls.path_for(provider_id)
        with AtomicYaml.with_lock(cls.lock_path(provider_id)):
            current = AtomicYaml.load_yaml(path)
            provider_values = current.setdefault(provider_id, {})
            if not isinstance(provider_values, dict):
                raise SecretsError(f"Secrets file {path}: '{provider_id}' must be a mapping")
            result = dict(callback({str(key): value for key, value in provider_values.items() if value is not None}))
            cls._validate_values(provider_id, result)
            current[provider_id] = result
            AtomicYaml.atomic_write(path, current)
            os.chmod(path, 0o600)
            return result

    @classmethod
    def get(cls, provider_id: str, key: str) -> str | None:
        return cls.read(provider_id).get(str(key))

    @classmethod
    def keys_set(cls, provider_id: str) -> list[str]:
        return list(cls.read(provider_id).keys())

    @staticmethod
    def _validate_values(provider_id: str, values: Mapping[str, Any] | None) -> None:
        if not values:
            return
        for key, value in values.items():
            if value is None:
                continue
            if not isinstance(value, str):
                raise SecretsError(f"Secret '{provider_id}.{key}' must be a string, got {type(value).__name__}")
