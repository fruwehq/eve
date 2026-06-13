from __future__ import annotations

import json
import os


def load_env() -> dict[str, str]:
    raw = os.environ.get("EVE_TF_ENV_JSON")
    if raw is None:
        raise RuntimeError("EVE_TF_ENV_JSON is required")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("EVE_TF_ENV_JSON must be a JSON object")
    return {str(key): "" if value is None else str(value) for key, value in parsed.items()}


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def print_kv(key: str, value: object) -> None:
    print(f"export {key}={quote(value)};")


def normalize_path(value: str) -> str:
    if not value:
        return value
    home = os.environ.get("HOME", "")
    if value == "~":
        return home
    if value.startswith("~/"):
        return home + value[1:]
    if value == "$HOME":
        return home
    if value.startswith("$HOME/"):
        return home + value[5:]
    if value == "$(HOME)":
        return home
    if value.startswith("$(HOME)/"):
        return home + value[7:]
    return value
