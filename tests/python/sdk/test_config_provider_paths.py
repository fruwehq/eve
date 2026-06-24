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
        {"id": "p1", "bootstrap": {"sudo_password_env": "P1_PW"}},
        {"id": "p2"},  # declares no bootstrap
    ]
    monkeypatch.setattr(
        plugin_manifest.PluginManifest, "load_all",
        classmethod(lambda cls, kind=None: fake),
    )
    monkeypatch.setenv("P1_PW", "s3cret")

    assert ConfigEnv.bootstrap_sudo_password("p1") == "s3cret"   # declared + set
    monkeypatch.delenv("P1_PW")
    assert ConfigEnv.bootstrap_sudo_password("p1") == ""          # declared, unset
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
