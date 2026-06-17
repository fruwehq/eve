"""Provider-declared env-var emission (v4.0 core-boundary Chunk B).

Provider manifests declare ``env_emission`` entries that tell CoreEmit which
provider-specific env vars to emit for every resolved instance and how to
derive each value from the resolved context. Core evaluates the UNION of all
provider-declared entries against the instance context, producing the same key
set + values as the former hardcoded provider-literal branches in
``resolve.emit_env`` / ``profile_resolve.emit_env`` — without any provider id
literal in core.

Entry shape (declared in a provider manifest's top-level ``env_emission`` list):

.. code-block:: yaml

   env_emission:
     - name: SOME_IMAGE_PROJECT       # ENV var name
       from: os.image_project         # dotted ref into resolved context
       default: ""                    # value when all refs are empty
     - name: SOME_OS_ID
       from: os.os_id
       default: 0
       tostring: true                 # JSON-encode (mirror jq tostring)
     - name: SOME_URL
       from: os.image_url
       default: ""
       match_provider: true          # only emit when declaring provider == instance provider
     - name: SOME_HOST
       from:                         # coalesce list — first non-empty wins
         - provider_config.host
         - provider_config.ip
         - env:SOME_HOST             # env:<NAME> reads os.environ
         - location.host
       default: ""

Ref prefixes: ``os.``, ``location.``, ``provider_config.``, ``machine.defaults.``,
``env:`` (the last is an environment-variable lookup, not a context path).
"""

from __future__ import annotations

import json
import os
from typing import Any


def evaluate_provider_env(
    resolved: dict[str, Any],
    provider_plugins: list[dict[str, Any]],
) -> dict[str, str]:
    """Evaluate all provider-declared ``env_emission`` entries.

    Returns ``{ENV_VAR: value}`` for every declared key across all loaded
    provider manifests. ``match_provider`` keys emit ``""`` when the declaring
    provider ≠ the instance's provider. Non-applicable providers naturally
    produce empty/default values (reproduces today's fixed key set).
    """
    instance_provider = str((resolved.get("machine") or {}).get("provider") or "")
    os_doc = resolved.get("os") or {}
    location = resolved.get("location") or {}
    locp = location.get(instance_provider) or {}
    provider_config = resolved.get("provider_config") or {}
    machine_defaults = ((resolved.get("machine") or {}).get("defaults")) or {}

    context: dict[str, Any] = {
        "os": os_doc,
        "location": locp,
        "provider_config": provider_config,
    }
    # machine.defaults is a nested ref
    context["machine"] = {"defaults": machine_defaults}

    result: dict[str, str] = {}
    for plugin in provider_plugins:
        entries = plugin.get("env_emission") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            name = str(entry["name"])
            if entry.get("match_provider"):
                # match_provider: only set when this provider IS the instance
                # provider; otherwise initialize to "" without overwriting a
                # value set by the matching provider.
                if plugin.get("id") == instance_provider:
                    result[name] = _evaluate_entry(entry, context)
                elif name not in result:
                    result[name] = ""
            else:
                result[name] = _evaluate_entry(entry, context)
    return result


def _evaluate_entry(entry: dict[str, Any], context: dict[str, Any]) -> str:
    """Resolve one ``env_emission`` entry to its string value."""
    refs: Any = entry.get("from")
    if isinstance(refs, str):
        refs = [refs]
    elif not isinstance(refs, list):
        refs = []

    for ref in refs:
        value = _resolve_ref(str(ref), context)
        if value is not None and value != "" and value is not False:
            return _format(value, entry)

    default = entry.get("default", "")
    return _format(default, entry)


def _resolve_ref(ref: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted ref (e.g. ``os.image_project``) or ``env:NAME``."""
    if ref.startswith("env:"):
        env_name = ref[4:]
        return os.environ.get(env_name)
    current: Any = context
    for part in ref.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _format(value: Any, entry: dict[str, Any]) -> str:
    """Convert a value to its string form, honoring ``tostring``."""
    if entry.get("tostring"):
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, str):
            return value
        return json.dumps(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
