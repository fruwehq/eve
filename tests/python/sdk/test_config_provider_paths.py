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
