from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.config import ConfigEnv


def test_config_env_expands_provider_path_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A provider's type:path config field gets ~ expansion without core naming it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    defaults = tmp_path / "defaults.yaml"
    # SSH key (core, is_path) expands; mock-cloud region (string) does not.
    defaults.write_text(
        "global:\n  ssh_public_key_file: ~/id.pub\nmock-cloud:\n  region: r1\n",
        encoding="utf-8",
    )
    env = ConfigEnv.environment(defaults, tmp_path / "missing.yaml")
    assert env["SSH_PUBLIC_KEY_FILE"] == str(tmp_path / "home/id.pub")
    # MOCK_REGION is a string field -> no expansion, value passes through.
    assert env["MOCK_REGION"] == "r1"


def test_config_env_has_no_provider_env_names_hardcoded() -> None:
    """Core no longer carries provider env-var literals (they live in manifests)."""
    import inspect

    from eve_sdk import config as cfg
    src = inspect.getsource(cfg)
    for provider_env in (
        "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE",
        "GOOGLE_APPLICATION_CREDENTIALS", "TRUENAS_SSH_PRIVATE_KEY_FILE",
        "RASPBERRY_PI_HOST", "RASPBERRY_PI_IP",
        "raspberry_pi",
    ):
        assert provider_env not in src, f"{provider_env!r} should not be in core config.py"
    assert not hasattr(cfg.ConfigEnv, "PATH_ENV_NAMES")


def test_bootstrap_sudo_password_reads_declared_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Core reads the provider-declared bootstrap password env, naming no provider."""
    from eve_sdk import plugin_manifest

    fake = [
        {
            "id": "p1",
            "bootstrap": {"sudo_password_env": "P1_PW"},
            "config_schema": {
                "secrets": {
                    "password": {"env_var": "P1_PW", "type": "string"}
                }
            },
        },
        {"id": "p2"},  # declares no bootstrap
    ]
    monkeypatch.setattr(
        plugin_manifest.PluginManifest, "load_all",
        classmethod(lambda cls, kind=None: fake),
    )
    monkeypatch.setattr(
        "eve_sdk.provider_command.Secrets.read",
        staticmethod(lambda name: {"password": "s3cret"} if name == "p1" else {}),
    )

    assert ConfigEnv.bootstrap_sudo_password("p1") == "s3cret"   # declared + set
    assert ConfigEnv.bootstrap_sudo_password("p2") == ""          # no bootstrap block
    assert ConfigEnv.bootstrap_sudo_password("missing") == ""     # unknown provider

    import inspect
    src = inspect.getsource(ConfigEnv.bootstrap_sudo_password)
    assert "RASPBERRY_PI" not in src, "core must not name a provider's password env"


def test_plugin_provision_env_names_aggregates_config_and_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provision env names cover config + ALL secrets (incl. string), generically."""
    from eve_sdk import plugin_manifest

    fake = [{
        "id": "pkg",
        "config_schema": {
            "config": {"ver": {"env_var": "PKG_VERSION"}},
            "secrets": {
                "password": {"type": "string", "env_var": "PKG_PASSWORD"},
                "keyfile": {"type": "path", "env_var": "PKG_KEY_FILE"},
            },
        },
    }]
    monkeypatch.setattr(
        plugin_manifest.PluginManifest, "load_all",
        classmethod(lambda cls, kind=None: fake if kind == "package" else []),
    )
    names = ConfigEnv.plugin_provision_env_names(kinds=("package",))
    # string secret IS included here (unlike _plugin_mappings/config-env).
    assert names == ["PKG_KEY_FILE", "PKG_PASSWORD", "PKG_VERSION"]


def test_provision_env_payload_includes_only_selected_package_names() -> None:
    environment = {
        "EPHEMERAL_DISPLAY_RESOLUTION": "1920x1080",
        "SELECTED_PASSWORD": "secret-one",
        "UNRELATED_PASSWORD": "secret-two",
    }

    payload = ConfigEnv.provision_env_payload(
        "windows-secret", environment, ["SELECTED_PASSWORD"]
    )

    assert payload == {
        "windows_password": "windows-secret",
        "display_resolution": "1920x1080",
        "selected_password": "secret-one",
    }


def test_package_stage_env_names_only_package_type_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only package type:path config fields are staged; provider paths excluded."""
    from eve_sdk import plugin_manifest

    def fake_load_all(cls: object, kind: str | None = None) -> list[dict[str, object]]:
        if kind == "package":
            return [{
                "id": "pkg",
                "config_schema": {"config": {
                    "bundle": {"type": "path", "env_var": "PKG_BUNDLE"},
                    "name": {"type": "string", "env_var": "PKG_NAME"},
                }},
            }]
        if kind == "provider":
            return [{
                "id": "prov",
                "config_schema": {"config": {
                    "creds": {"type": "path", "env_var": "PROV_CREDS"},
                }},
            }]
        return []

    monkeypatch.setattr(plugin_manifest.PluginManifest, "load_all", classmethod(fake_load_all))
    # PKG_BUNDLE (package type:path) only — PKG_NAME (string) and PROV_CREDS
    # (provider type:path, local-only credential) excluded.
    assert ConfigEnv.package_stage_env_names() == ["PKG_BUNDLE"]


def test_instance_package_env_maps_overrides_via_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-instance package_config maps field->env_var via the package manifest (§16)."""
    from eve_sdk import plugin_manifest

    fake = [{
        "id": "streamer",
        "config_schema": {"config": {
            "version": {"env_var": "STREAMER_VERSION"},
            "bitrate": {"env_var": "STREAMER_BITRATE"},
        }},
    }]
    monkeypatch.setattr(
        plugin_manifest.PluginManifest, "load_all",
        classmethod(lambda cls, kind=None: fake if kind == "package" else []),
    )
    out = ConfigEnv.instance_package_env({
        "streamer": {"version": "9.9", "bitrate": 20000},
        "unknown-pkg": {"x": "y"},          # unknown package -> skipped
        "streamer-typo-field": {},          # ignored (not a real pkg)
    })
    assert out == {"STREAMER_VERSION": "9.9", "STREAMER_BITRATE": "20000"}
    assert ConfigEnv.instance_package_env({}) == {}


def test_package_environment_is_operation_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eve_sdk import plugin_manifest
    from eve_sdk.package_dispatch import resolved_package_environment

    plugin = {
        "id": "streamer",
        "config_schema": {
            "config": {"version": {"env_var": "STREAMER_VERSION"}},
            "secrets": {"token": {"env_var": "STREAMER_TOKEN"}},
        },
    }
    other_plugin = {
        "id": "other",
        "config_schema": {
            "config": {"version": {"env_var": "OTHER_VERSION"}},
        },
    }
    monkeypatch.setattr(
        plugin_manifest.PluginManifest,
        "load_all",
        classmethod(
            lambda cls, kind=None: [plugin, other_plugin]
            if kind == "package"
            else []
        ),
    )
    monkeypatch.setattr(
        ConfigEnv,
        "environment",
        classmethod(
            lambda cls, *a, **k: {
                "OTHER_PLUGIN_TOKEN": "must-not-leak",
                "STREAMER_VERSION": "1.0",
            }
        ),
    )
    monkeypatch.setattr(
        "eve_sdk.provider_command.Secrets.read",
        staticmethod(lambda name: {"token": "secret"}),
    )
    monkeypatch.setenv("UNDECLARED_AMBIENT_TOKEN", "must-not-leak")

    env = resolved_package_environment(
        plugin,
        {
            "instance": {"name": "test"},
            "package_config": {
                "other": {"version": "must-not-leak"},
                "streamer": {"version": "2.0"},
            },
        },
    )

    assert env["STREAMER_TOKEN"] == "secret"
    assert env["STREAMER_VERSION"] == "2.0"
    assert "OTHER_PLUGIN_TOKEN" not in env
    assert "OTHER_VERSION" not in env
    assert "UNDECLARED_AMBIENT_TOKEN" not in env


def test_provider_environment_is_operation_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eve_sdk.provider_command import resolved_provider_environment

    plugin = {
        "id": "cloud",
        "config_schema": {
            "config": {"region": {"env_var": "CLOUD_REGION"}},
            "secrets": {"token": {"env_var": "CLOUD_TOKEN"}},
        },
    }
    monkeypatch.setattr(
        ConfigEnv,
        "environment",
        classmethod(
            lambda cls, *a, **k: {
                "CLOUD_REGION": "r1",
                "OTHER_PROVIDER_TOKEN": "must-not-leak",
            }
        ),
    )
    monkeypatch.setattr(
        "eve_sdk.provider_command.Secrets.read",
        staticmethod(lambda name: {"token": "secret"}),
    )
    monkeypatch.setenv("UNDECLARED_AMBIENT_TOKEN", "must-not-leak")

    env = resolved_provider_environment("cloud", plugin)

    assert env["CLOUD_REGION"] == "r1"
    assert env["CLOUD_TOKEN"] == "secret"
    assert "OTHER_PROVIDER_TOKEN" not in env
    assert "UNDECLARED_AMBIENT_TOKEN" not in env
