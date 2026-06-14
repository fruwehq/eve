"""Shared helpers for the package-* dispatcher scripts.

Consolidates the pieces that the original bash/sh scripts duplicated verbatim:
the CLIXML/Objs detail scrubber, the status-probe status extraction, the
optional profile-resolve + human-user resolution, the Linux human-run context
builder, and jq-default-compatible JSON emission.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Characters allowed for a unix user name: letters, digits, dot, underscore,
# hyphen. Matches the bash ``case "$human_user" in *[!a-zA-Z0-9._-]*)`` guard.
_HUMAN_USER_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def emit_json(obj: object) -> None:
    """Print ``obj`` as JSON matching jq's default pretty-printed output.

    jq's default format is 2-space indent, keys in insertion order, UTF-8
    passthrough, with a trailing newline. ``json.dumps(indent=2,
    ensure_ascii=False)`` matches byte-for-byte.
    """
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def clean_clixml_details(output: str) -> str:
    """Strip ``\\r`` and CLIXML/<Objs> wrapper noise from captured SSH output.

    Mirrors the bash ``clean_details`` awk: remove all carriage returns, then
    drop lines that are CLIXML preamble, ``<Objs``/``<Obj`` elements,
    ``</Objs>``, or contain ``_x000D__``. The caller strips trailing newlines
    (as bash ``$(...)`` does).
    """
    stripped = output.replace("\r", "")
    lines: list[str] = []
    for line in stripped.split("\n"):
        if line.startswith("#< CLIXML"):
            continue
        if line.startswith("<Objs "):
            continue
        if line.startswith("<Obj "):
            continue
        if line.startswith("</Objs>"):
            continue
        if "_x000D__" in line:
            continue
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


def first_status(details: str, valid: set[str]) -> str:
    """Return the first line of ``details`` that is exactly a status keyword.

    Mirrors ``awk '/^(...)$/ {print; exit}'``. Returns ``""`` if no line
    matches.
    """
    for line in details.split("\n"):
        if line in valid:
            return line
    return ""


def optional_profile_env(root: Path, profile: str) -> dict[str, str] | None:
    """Resolve a profile via ``scripts/profile-resolve`` returning ``None`` on failure.

    Mirrors the bash ``if resolved_env=$(... 2>/dev/null); then ... else ... fi``
    pattern: stderr is suppressed (not propagated), and a non-zero exit returns
    ``None`` rather than raising.
    """
    result = subprocess.run(
        [str(root / "scripts/profile-resolve"), "--profile", profile, "--emit", "env"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return None
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def resolve_human_user(root: Path, profile: str, script_name: str) -> str:
    """Resolve the human user name for a profile.

    Mirrors the bash sequence: try profile-resolve (failure is OK), take
    ``VM_USER_NAME`` then ``SSH_USER``, fall back to ``id -un``, and validate
    the charset. Exits 2 with the original ``<script_name>: unsupported VM user
    name`` message on an invalid name.
    """
    resolved = optional_profile_env(root, profile)
    vm_user = ""
    ssh_user = ""
    if resolved is not None:
        vm_user = resolved.get("VM_USER_NAME", "")
        ssh_user = resolved.get("SSH_USER", "")
    human_user = vm_user or ssh_user
    if not human_user:
        human_user = subprocess.check_output(["id", "-un"], text=True).strip()
    if not _HUMAN_USER_RE.match(human_user):
        print(f"{script_name}: unsupported VM user name: {human_user}", file=sys.stderr)
        raise SystemExit(2)
    return human_user


def build_linux_human_context(human_user: str, remote_command: str, include_cargo: bool) -> str:
    """Build the remote bash wrapper that exports the human user's environment.

    Mirrors the unquoted heredoc in package-status-command / package-down-command:
    only ``$HUMAN_USER`` and ``$REMOTE_COMMAND`` are expanded; every ``\\$``
    becomes a literal ``$``. When ``include_cargo`` is True the PATH includes
    ``.cargo/bin`` (package-status-command); otherwise it does not
    (package-down-command).
    """
    cargo = ":$EVE_HUMAN_HOME/.cargo/bin" if include_cargo else ""
    template = (
        "set -eu\n"
        'EVE_HUMAN_USER="{h}"\n'
        'EVE_HUMAN_HOME=$(getent passwd "$EVE_HUMAN_USER" | cut -d: -f6)\n'
        'EVE_HUMAN_UID=$(id -u "$EVE_HUMAN_USER")\n'
        "export EVE_HUMAN_USER EVE_HUMAN_HOME EVE_HUMAN_UID\n"
        'export HOME="$EVE_HUMAN_HOME"\n'
        'export PATH="$EVE_HUMAN_HOME/.local/bin{cargo}:$PATH"\n'
        "eve_human_run() {{\n"
        '  sudo -H -u "$EVE_HUMAN_USER" env \\\n'
        '    HOME="$EVE_HUMAN_HOME" \\\n'
        '    USER="$EVE_HUMAN_USER" \\\n'
        '    LOGNAME="$EVE_HUMAN_USER" \\\n'
        '    PATH="$EVE_HUMAN_HOME/.local/bin{cargo}:$PATH" \\\n'
        '    XDG_RUNTIME_DIR="/run/user/$EVE_HUMAN_UID" \\\n'
        '    "$@"\n'
        "}}\n"
        "{cmd}"
    )
    return template.format(h=human_user, cargo=cargo, cmd=remote_command)


def run_status_probe(
    ssh_helper: str,
    profile: str,
    remote_command: str,
) -> tuple[int, str]:
    """Run a status probe via ``ssh_helper`` and return (exit_status, details).

    Mirrors the bash ``set +e; output="$(... 2>&1); exit_status=$?; set -e``
    capture: stdout and stderr are merged, trailing newlines are stripped
    (command-substitution semantics), and CLIXML noise is scrubbed.
    """
    result = subprocess.run(
        [ssh_helper, profile, "--", remote_command],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )
    output = result.stdout.rstrip("\n")
    details = clean_clixml_details(output)
    return result.returncode, details


def quote_ps_single(value: str) -> str:
    """Single-quote a string for PowerShell (double internal quotes).

    Mirrors the bash ``quote_ps_string`` helper.
    """
    return "'" + value.replace("'", "''") + "'"


def encode_ps_command(script: str) -> str:
    """Encode a PowerShell script as a ``-EncodedCommand`` argument.

    Mirrors ``iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\\n'``.
    """
    import base64
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")
