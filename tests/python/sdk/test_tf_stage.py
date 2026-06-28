"""Staging of externalized provider stacks for the terraform read path.

The read/power commands (status, ip, …) call `scripts/tf-stage` →
`stage_provider_stacks`, which vendors the provider's terramate stacks the same
way the write path (tf-init) does. These tests cover the pure file-staging
logic (`prepare_provider_stacks` + helpers) without invoking terramate, so they
stay hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.tf_dispatch import (
    _generated_backend_present,
    _staged_dir_current,
    prepare_provider_stacks,
)

PROVIDER_MANIFEST = """\
api_version: eve.plugin/v1
kind: provider
id: acme-tf
display_name: Acme TF
commands:
  resolve: {exec: commands/provider-command, args: [resolve]}
  init: {exec: commands/provider-command, args: [init]}
  plan: {exec: commands/provider-command, args: [plan]}
  up: {exec: commands/provider-command, args: [up]}
  down: {exec: commands/provider-command, args: [down]}
  start: {exec: commands/provider-command, args: [start]}
  stop: {exec: commands/provider-command, args: [stop]}
  status: {exec: commands/provider-command, args: [status]}
  ip: {exec: commands/provider-command, args: [ip]}
  ssh: {exec: commands/provider-command, args: [ssh]}
  validate: {exec: commands/provider-command, args: [validate]}
access:
  ubuntu:
    bootstrap_user: {env: VM_USER_NAME}
    provision_user: {env: VM_USER_NAME}
    human_user: {env: VM_USER_NAME, fallback: provision_user}
supports:
  engines: [terraform]
  kinds: [vm]
env: []
"""


@pytest.fixture()
def staged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A source plugin root (provider + shared sibling) and a repo root.

    Returns ``(repo_root, source_provider_dir)``. Discovery is pinned to the
    source root via EVE_PLUGIN_ROOTS(_EXCLUSIVE) so prepare_provider_stacks
    resolves ``acme-tf`` to it.
    """
    source_root = tmp_path / "source"
    provider = source_root / "acme-tf"
    (provider / "stacks" / "svc").mkdir(parents=True)
    (provider / "eve-plugin.yaml").write_text(PROVIDER_MANIFEST, encoding="utf-8")
    (provider / "stacks" / "svc" / "main.tf").write_text("# svc\n", encoding="utf-8")
    # Manifest validation requires each declared command's exec to exist.
    commands = provider / "commands"
    commands.mkdir()
    stub = commands / "provider-command"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    # A shared sibling dir (leading underscore) the staging must also copy.
    shared = source_root / "_tf-shared"
    shared.mkdir()
    (shared / "common.tf").write_text("# shared\n", encoding="utf-8")

    monkeypatch.setenv("EVE_PLUGIN_ROOTS", str(source_root))
    monkeypatch.setenv("EVE_PLUGIN_ROOTS_EXCLUSIVE", "1")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root, provider


def test_stages_provider_and_shared_dirs(staged: tuple[Path, Path]) -> None:
    repo_root, _ = staged
    changed = prepare_provider_stacks(repo_root, "acme-tf")
    assert changed is True
    dest = repo_root / "plugins" / "providers"
    assert (dest / "acme-tf" / "stacks" / "svc" / "main.tf").read_text() == "# svc\n"
    assert (dest / "_tf-shared" / "common.tf").read_text() == "# shared\n"
    # The manifest itself is never vendored into the stack tree.
    assert not (dest / "acme-tf" / "eve-plugin.yaml").exists()


def test_idempotent_no_rewrite_when_current(staged: tuple[Path, Path]) -> None:
    repo_root, _ = staged
    assert prepare_provider_stacks(repo_root, "acme-tf") is True
    # Already current → no work, no change reported (so callers skip generate).
    assert prepare_provider_stacks(repo_root, "acme-tf") is False
    assert prepare_provider_stacks(repo_root, "acme-tf") is False


def test_generated_files_survive_idempotent_calls(staged: tuple[Path, Path]) -> None:
    """A generated z_backend.tf (destination-only) must not be wiped when the
    source is unchanged — that's what keeps frequent status polls from forcing
    a re-init."""
    repo_root, _ = staged
    prepare_provider_stacks(repo_root, "acme-tf")
    generated = repo_root / "plugins" / "providers" / "acme-tf" / "stacks" / "svc" / "z_backend.tf"
    generated.write_text("# generated\n", encoding="utf-8")
    assert _generated_backend_present(repo_root, "acme-tf") is True
    # Re-staging while current is a no-op → generated file is preserved.
    assert prepare_provider_stacks(repo_root, "acme-tf") is False
    assert generated.read_text() == "# generated\n"


def test_restages_when_source_changes(staged: tuple[Path, Path]) -> None:
    repo_root, provider = staged
    prepare_provider_stacks(repo_root, "acme-tf")
    (provider / "stacks" / "svc" / "main.tf").write_text("# svc v2\n", encoding="utf-8")
    assert prepare_provider_stacks(repo_root, "acme-tf") is True
    dest_main = repo_root / "plugins" / "providers" / "acme-tf" / "stacks" / "svc" / "main.tf"
    assert dest_main.read_text() == "# svc v2\n"


def test_unknown_provider_is_noop(staged: tuple[Path, Path]) -> None:
    repo_root, _ = staged
    assert prepare_provider_stacks(repo_root, "does-not-exist") is False
    assert not (repo_root / "plugins" / "providers").exists()


def test_staged_dir_current_ignores_destination_only_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "stacks").mkdir(parents=True)
    (src / "stacks" / "main.tf").write_text("x\n", encoding="utf-8")
    (dst / "stacks").mkdir(parents=True)
    (dst / "stacks" / "main.tf").write_text("x\n", encoding="utf-8")
    (dst / "stacks" / "z_backend.tf").write_text("gen\n", encoding="utf-8")  # dest-only
    assert _staged_dir_current(src, dst) is True
    # A genuine content drift in a source-tracked file is not current.
    (dst / "stacks" / "main.tf").write_text("y\n", encoding="utf-8")
    assert _staged_dir_current(src, dst) is False
