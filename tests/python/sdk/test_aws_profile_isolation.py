"""A profile-only provider cannot consume ambient or Eve-managed credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from eve_sdk.config import ConfigEnv
from eve_sdk.dispatch import process_environment
from eve_sdk.fsm import EveFsm, provider_configured_resolver
from eve_sdk.profile_resolve import apply_provider_secrets
from eve_sdk.provider_command import resolved_provider_environment


@pytest.fixture
def profile_plugin() -> dict[str, Any]:
    return {
        "id": "aws",
        "kind": "provider",
        "config_schema": {"config": {"profile": {"env_var": "AWS_PROFILE", "required": True}}},
    }


def reject_secret_read(*args: Any) -> None:
    raise AssertionError("A provider without declared secrets must not read a secret store")


@pytest.mark.parametrize("profile", ["", "named-profile"])
def test_aws_profile_is_the_only_configuration_path(
    monkeypatch: pytest.MonkeyPatch, profile_plugin: dict[str, Any], profile: str,
) -> None:
    ambient = {
        "AWS_ACCESS_KEY_ID": "ignored-access",
        "AWS_PROFILE": "ignored-ambient-profile",
        "AWS_SECRET_ACCESS_KEY": "ignored-secret",
        "AWS_SESSION_TOKEN": "ignored-token",
    }
    for name, value in ambient.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(ConfigEnv, "environment", classmethod(lambda cls: {"AWS_PROFILE": profile}))
    monkeypatch.setattr("eve_sdk.provider_command.Secrets.read", reject_secret_read)
    monkeypatch.setattr("eve_sdk.provider_command._load_public_plugin", lambda *args: profile_plugin)

    assert not set(ambient) & process_environment().keys()
    before = dict(os.environ)
    env = resolved_provider_environment("aws", profile_plugin)
    assert env["AWS_PROFILE"] == profile
    assert not (set(ambient) - {"AWS_PROFILE"}) & env.keys()
    assert dict(os.environ) == before

    fsm = EveFsm(provider_configured_resolver())
    fsm.load("provider", (Path(__file__).resolve().parents[3] / "core/fsm/provider.yaml").read_text())
    fsm.fire("provider", "aws", "resolve")
    assert fsm.state("provider", "aws") == ("unreachable" if profile else "unconfigured")


def test_legacy_profile_resolution_does_not_read_aws_secrets(
    monkeypatch: pytest.MonkeyPatch, profile_plugin: dict[str, Any],
) -> None:
    monkeypatch.setattr("eve_sdk.profile_resolve.PluginManifest.load_all", lambda *args: [profile_plugin])
    monkeypatch.setattr("eve_sdk.profile_resolve.Secrets.read", reject_secret_read)
    before = dict(os.environ)
    apply_provider_secrets({"machine": {"provider": "aws"}})
    assert dict(os.environ) == before


def test_legacy_profile_resolution_preserves_other_provider_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = {"id": "cloud", "config_schema": {"secrets": {"token": {"env_var": "CLOUD_TOKEN"}}}}
    monkeypatch.setattr("eve_sdk.profile_resolve.PluginManifest.load_all", lambda *args: [plugin])
    monkeypatch.setattr("eve_sdk.profile_resolve.Secrets.read", lambda *args: {"CLOUD_TOKEN": "test-token"})
    monkeypatch.delenv("CLOUD_TOKEN", raising=False)
    apply_provider_secrets({"machine": {"provider": "cloud"}})
    assert os.environ["CLOUD_TOKEN"] == "test-token"
    monkeypatch.delenv("CLOUD_TOKEN")


def test_profile_only_settings_do_not_read_or_write_secrets(
    monkeypatch: pytest.MonkeyPatch, profile_plugin: dict[str, Any],
) -> None:
    from tui import settings

    monkeypatch.setattr(settings, "load_provider_schema", lambda *args: profile_plugin["config_schema"])
    monkeypatch.setattr(settings.Secrets, "read", reject_secret_read)
    monkeypatch.setattr(settings.Secrets, "keys_set", reject_secret_read)
    monkeypatch.setattr(settings.Secrets, "update", reject_secret_read)
    assert settings.load_provider_secrets("aws") == {}
    assert settings.load_provider_secret_keys("aws") == []
    with pytest.raises(RuntimeError, match="not declared"):
        settings.save_provider_secret("aws", "access_key_id", "ignored-value")
