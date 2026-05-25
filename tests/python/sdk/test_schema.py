from __future__ import annotations

import pytest

from eve_sdk.schema import SchemaValidationError, validate_def, validate_schema


def test_schema_validates_default_state_shape() -> None:
    validate_schema(
        "observed-state.schema.json",
        {
            "instance": "demo",
            "desired_state": "unknown",
            "provider_state": "unknown",
            "provision_state": "unknown",
            "package_state": {},
            "observed_state": {},
            "operation_history": [],
            "last_operation": None,
            "last_error": None,
        },
        "Observed state",
    )


def test_schema_rejects_invalid_provider_command_output() -> None:
    with pytest.raises(SchemaValidationError, match="command output failed schema validation"):
        validate_def("command-io.schema.json", "provider_command_output", {"status": "bogus"}, "command output")
