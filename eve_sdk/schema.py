from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from eve_sdk.workdir import Workdir


class SchemaValidationError(Exception):
    pass


def schema_dir() -> Path:
    return Workdir.repo_root() / "core/schema"


def load_schema(name: str) -> dict[str, Any]:
    path = schema_dir() / name
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SchemaValidationError(f"Schema file not found: {path}") from error
    if not isinstance(loaded, dict):
        raise SchemaValidationError(f"Schema file {path} must contain a JSON object")
    return loaded


def validator_for(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise SchemaValidationError(f"Schema {name} is invalid: {error.message}") from error
    return Draft202012Validator(schema)


def validate_schema(name: str, data: Any, label: str) -> None:
    validator = validator_for(name)
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if errors:
        raise SchemaValidationError(format_errors(label, errors))


def validate_def(schema_name: str, def_name: str, data: Any, label: str) -> None:
    raw = load_schema(schema_name)
    defs = raw.get("$defs") or raw.get("defs") or {}
    if not isinstance(defs, dict) or def_name not in defs:
        raise SchemaValidationError(f"Unknown $defs entry: {def_name}")
    schema = defs[def_name]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise SchemaValidationError(f"Schema definition {def_name} is invalid: {error.message}") from error
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
    if errors:
        raise SchemaValidationError(format_errors(label, errors))


def validate_json_schema_fragment(fragment: dict[str, Any], label: str) -> None:
    try:
        Draft202012Validator.check_schema(fragment)
    except SchemaError as error:
        raise SchemaValidationError(f"{label} failed schema validation: {error.message}") from error


def format_errors(label: str, errors: list[ValidationError]) -> str:
    lines = [f"{label} failed schema validation:"]
    for error in errors:
        pointer = "/" + "/".join(str(part) for part in error.absolute_path)
        lines.append(f"  {pointer if pointer != '/' else '/'}: {error.message}")
    return "\n".join(lines)
