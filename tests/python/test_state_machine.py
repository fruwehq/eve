"""Regression tests for state-machine rules moved to core/sdk/state-machine.rb.

These tests pin the behavior of the 6 state-machine functions that were
extracted from scripts/egame-tui into core/sdk/state-machine.rb. They
verify the Ruby implementation matches the original Python behavior.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def ruby_eval(code: str) -> str:
    result = subprocess.run(
        ["ruby", "-I", str(ROOT / "core"), "-r", "sdk", "-e", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def ruby_state_machine(method: str, *args_json: str) -> str:
    parts = [f'include Egame::SDK']
    parts.append(f'result = StateMachine.{method}({", ".join(args_json)})')
    parts.append('puts result.inspect')
    return ruby_eval("; ".join(parts))


# ---------------------------------------------------------------------------
# normalize_provider_state
# ---------------------------------------------------------------------------

class TestNormalizeProviderState:
    def test_running(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"running"') == '"running"'

    def test_stopped(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"stopped"') == '"stopped"'

    def test_not_created(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"not created"') == '"absent"'

    def test_not_created_hyphen(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"not-created"') == '"absent"'

    def test_absent(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"absent"') == '"absent"'

    def test_unreachable(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"unreachable"') == '"error"'

    def test_error(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"error"') == '"error"'

    def test_failed(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"failed"') == '"error"'

    def test_unknown_passthrough(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"transitioning"') == '"transitioning"'

    def test_empty_string(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '""') == '"unknown"'

    def test_whitespace(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"  "') == '"unknown"'

    def test_case_insensitive(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"Running"') == '"running"'
        assert ruby_state_machine("normalize_provider_state", '"STOPPED"') == '"stopped"'

    def test_surrounding_whitespace(self) -> None:
        assert ruby_state_machine("normalize_provider_state", '"  running  "') == '"running"'


# ---------------------------------------------------------------------------
# effective_provider_state
# ---------------------------------------------------------------------------

class TestEffectiveProviderState:
    def _eps(self, state_json: str) -> str:
        return ruby_state_machine("effective_provider_state", state_json)

    def test_running(self) -> None:
        assert self._eps('{"provider_state"=>"running"}') == '"running"'

    def test_stopped(self) -> None:
        assert self._eps('{"provider_state"=>"stopped","desired_state"=>"stopped","provision_state"=>"unknown"}') == '"stopped"'

    def test_absent(self) -> None:
        assert self._eps('{"provider_state"=>"absent"}') == '"absent"'

    def test_error_with_running_desired_and_provisioned(self) -> None:
        assert self._eps('{"provider_state"=>"error","desired_state"=>"running","provision_state"=>"provisioned"}') == '"running"'

    def test_error_with_non_running_desired(self) -> None:
        assert self._eps('{"provider_state"=>"error","desired_state"=>"stopped","provision_state"=>"provisioned"}') == '"error"'

    def test_error_with_non_provisioned(self) -> None:
        assert self._eps('{"provider_state"=>"error","desired_state"=>"running","provision_state"=>"unknown"}') == '"error"'

    def test_unknown_defaults(self) -> None:
        assert self._eps('{}') == '"unknown"'


# ---------------------------------------------------------------------------
# should_apply_live_provider_state
# ---------------------------------------------------------------------------

class TestShouldApplyLiveProviderState:
    def _apply(self, status_json: str, live_state: str) -> str:
        return ruby_state_machine("should_apply_live_provider_state", status_json, f'"{live_state}"')

    def test_running_applied(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"unknown"}}', "running") == "true"

    def test_stopped_applied(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"unknown"}}', "stopped") == "true"

    def test_absent_applied(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"unknown"}}', "absent") == "true"

    def test_error_applied(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"unknown"}}', "error") == "true"

    def test_absent_not_applied_when_local_running(self) -> None:
        assert self._apply(
            '{"state"=>{"provider_state"=>"running","desired_state"=>"running","provision_state"=>"provisioned"}}',
            "absent",
        ) == "false"

    def test_error_not_applied_when_local_stopped(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"stopped"}}', "error") == "false"

    def test_error_not_applied_when_local_absent(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"absent"}}', "error") == "false"

    def test_error_applied_when_local_running(self) -> None:
        assert self._apply(
            '{"state"=>{"provider_state"=>"running","desired_state"=>"running","provision_state"=>"provisioned"}}',
            "error",
        ) == "true"

    def test_unknown_live_state_not_applied(self) -> None:
        assert self._apply('{"state"=>{"provider_state"=>"unknown"}}', "unknown") == "false"

    def test_non_dict_state_always_applied(self) -> None:
        assert self._apply('{"state"=>"not a dict"}', "running") == "true"

    def test_absent_not_applied_when_local_effectively_running(self) -> None:
        assert self._apply(
            '{"state"=>{"provider_state"=>"error","desired_state"=>"running","provision_state"=>"provisioned"}}',
            "absent",
        ) == "false"


# ---------------------------------------------------------------------------
# status_with_provider_state
# ---------------------------------------------------------------------------

class TestStatusWithProviderState:
    def _swps(self, status_json: str, provider_state: str) -> dict[str, Any]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.status_with_provider_state({status_json}, "{provider_state}"); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_sets_provider_state(self) -> None:
        result = self._swps('{"state"=>{}}', "running")
        assert result["state"]["provider_state"] == "running"

    def test_clears_last_error_on_running(self) -> None:
        result = self._swps('{"state"=>{"last_error"=>"old error"}}', "running")
        assert result["state"]["last_error"] is None

    def test_clears_last_error_on_stopped(self) -> None:
        result = self._swps('{"state"=>{"last_error"=>"old error"}}', "stopped")
        assert result["state"]["last_error"] is None

    def test_clears_last_error_on_absent(self) -> None:
        result = self._swps('{"state"=>{"last_error"=>"old error"}}', "absent")
        assert result["state"]["last_error"] is None

    def test_preserves_last_error_on_error(self) -> None:
        result = self._swps('{"state"=>{"last_error"=>"old error"}}', "error")
        assert result["state"]["last_error"] == "old error"

    def test_does_not_mutate_original(self) -> None:
        code = (
            'include Egame::SDK; '
            'original = {"state"=>{"provider_state"=>"unknown"}}; '
            'result = StateMachine.status_with_provider_state(original, "running"); '
            'puts JSON.generate({"original"=>original, "result"=>result})'
        )
        out = json.loads(ruby_eval(code))
        assert out["original"]["state"]["provider_state"] == "unknown"
        assert out["result"]["state"]["provider_state"] == "running"

    def test_creates_state_if_missing(self) -> None:
        result = self._swps('{}', "running")
        assert result["state"]["provider_state"] == "running"

    def test_preserves_other_fields(self) -> None:
        result = self._swps('{"state"=>{"provision_state"=>"provisioned"},"instance"=>{"name"=>"test"}}', "running")
        assert result["state"]["provision_state"] == "provisioned"
        assert result["instance"]["name"] == "test"


# ---------------------------------------------------------------------------
# status_with_observed_state
# ---------------------------------------------------------------------------

class TestStatusWithObservedState:
    def _swos(self, status_json: str, state_doc_json: str) -> dict[str, Any]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.status_with_observed_state({status_json}, {state_doc_json}); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_merges_observed_state(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"unknown"}}',
            '{"observed_state"=>{"provider_status"=>"running","ip"=>"1.2.3.4"}}',
        )
        assert result["observed_state"]["provider_status"] == "running"
        assert result["observed_state"]["ip"] == "1.2.3.4"
        assert result["state"]["observed_state"]["ip"] == "1.2.3.4"

    def test_updates_provider_state_from_running_observation(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"unknown"}}',
            '{"observed_state"=>{"provider_status"=>"running"}}',
        )
        assert result["state"]["provider_state"] == "running"

    def test_maps_unreachable_to_error(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"unknown"}}',
            '{"observed_state"=>{"provider_status"=>"unreachable"}}',
        )
        assert result["state"]["provider_state"] == "error"

    def test_does_not_apply_absent_over_running(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"running","desired_state"=>"running","provision_state"=>"provisioned"}}',
            '{"observed_state"=>{"provider_status"=>"absent"}}',
        )
        assert result["state"]["provider_state"] == "running"

    def test_empty_observed_state(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"stopped"}}',
            '{"observed_state"=>{}}',
        )
        assert result["state"]["provider_state"] == "stopped"

    def test_does_not_mutate_original(self) -> None:
        code = (
            'include Egame::SDK; '
            'original = {"state"=>{"provider_state"=>"unknown"}}; '
            'result = StateMachine.status_with_observed_state(original, {"observed_state"=>{"provider_status"=>"running"}}); '
            'puts JSON.generate({"original"=>original, "result"=>result})'
        )
        out = json.loads(ruby_eval(code))
        assert out["original"]["state"]["provider_state"] == "unknown"

    def test_no_observed_state_key(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"stopped"}}',
            '{}',
        )
        assert result["state"]["provider_state"] == "stopped"


# ---------------------------------------------------------------------------
# aggregate_summary
# ---------------------------------------------------------------------------

class TestAggregateSummary:
    def _agg(self, statuses_json: str) -> dict[str, int]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.aggregate_summary({statuses_json}); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_empty(self) -> None:
        result = self._agg('{}')
        assert result["running"] == 0
        assert result["stopped"] == 0
        assert result["failed"] == 0
        assert result["other"] == 0

    def test_counts_running(self) -> None:
        result = self._agg('{"a"=>{"state"=>{"provider_state"=>"running"}}}')
        assert result["running"] == 1
        assert result["stopped"] == 0

    def test_counts_stopped_and_absent(self) -> None:
        result = self._agg('{"a"=>{"state"=>{"provider_state"=>"stopped"}},"b"=>{"state"=>{"provider_state"=>"absent"}}}')
        assert result["running"] == 0
        assert result["stopped"] == 2

    def test_counts_failed_and_error(self) -> None:
        result = self._agg('{"a"=>{"state"=>{"provider_state"=>"failed"}},"b"=>{"state"=>{"provider_state"=>"error"}}}')
        assert result["failed"] == 2

    def test_counts_last_error_as_failed(self) -> None:
        result = self._agg('{"a"=>{"state"=>{"provider_state"=>"running","last_error"=>"boom"}}}')
        assert result["failed"] == 1
        assert result["running"] == 0

    def test_counts_unknown_as_other(self) -> None:
        result = self._agg('{"a"=>{"state"=>{"provider_state"=>"changing"}}}')
        assert result["other"] == 1

    def test_mixed_states(self) -> None:
        result = self._agg(
            '{"a"=>{"state"=>{"provider_state"=>"running"}},'
            '"b"=>{"state"=>{"provider_state"=>"stopped"}},'
            '"c"=>{"state"=>{"provider_state"=>"error"}},'
            '"d"=>{"state"=>{"provider_state"=>"changing"}}}'
        )
        assert result["running"] == 1
        assert result["stopped"] == 1
        assert result["failed"] == 1
        assert result["other"] == 1


# ---------------------------------------------------------------------------
# Edge cases: non-dict state / non-dict observed_state
# ---------------------------------------------------------------------------

class TestStatusWithProviderStateNonDictState:
    def _swps(self, status_json: str, provider_state: str) -> dict[str, Any]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.status_with_provider_state({status_json}, "{provider_state}"); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_non_dict_state_left_unchanged(self) -> None:
        result = self._swps('{"state"=>"running_string"}', "stopped")
        assert result["state"] == "running_string"

    def test_missing_state_creates_dict(self) -> None:
        result = self._swps('{}', "running")
        assert result["state"]["provider_state"] == "running"


class TestStatusWithObservedStateNonDict:
    def _swos(self, status_json: str, state_doc_json: str) -> dict[str, Any]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.status_with_observed_state({status_json}, {state_doc_json}); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_non_dict_observed_state_preserves_status(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"running"}}',
            '{"observed_state"=>"not a hash"}',
        )
        assert result == {"state": {"provider_state": "running"}}

    def test_non_dict_observed_state_does_not_set_state_key(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"stopped"}}',
            '{"observed_state"=>"string_value"}',
        )
        assert result == {"state": {"provider_state": "stopped"}}

    def test_nil_observed_state_preserves_status(self) -> None:
        result = self._swos(
            '{"state"=>{"provider_state"=>"running"}}',
            '{"observed_state"=>nil}',
        )
        assert result == {"state": {"provider_state": "running"}}

    def test_non_dict_status_state_preserves_status(self) -> None:
        result = self._swos(
            '{"state"=>"running_string"}',
            '{"observed_state"=>{"provider_status"=>"stopped"}}',
        )
        assert result == {"state": "running_string", "observed_state": {"provider_status": "stopped"}}

    def test_non_dict_observed_no_state_key_no_synthesis(self) -> None:
        result = self._swos(
            '{}',
            '{"observed_state"=>"not a hash"}',
        )
        assert result == {}

    def test_nil_state_with_valid_observed_adds_top_level_observed(self) -> None:
        result = self._swos(
            '{"state"=>nil}',
            '{"observed_state"=>{"provider_status"=>"running"}}',
        )
        assert result == {"state": None, "observed_state": {"provider_status": "running"}}

    def test_string_state_with_valid_observed_adds_top_level_observed(self) -> None:
        result = self._swos(
            '{"state"=>"running_string"}',
            '{"observed_state"=>{"provider_status"=>"stopped"}}',
        )
        assert result == {"state": "running_string", "observed_state": {"provider_status": "stopped"}}

    def test_missing_state_creates_dict_for_valid_observed(self) -> None:
        result = self._swos(
            '{}',
            '{"observed_state"=>{"provider_status"=>"running"}}',
        )
        assert result["state"]["provider_state"] == "running"
        assert "observed_state" in result

    def test_nil_state_not_overwritten_for_valid_observed(self) -> None:
        result = self._swos(
            '{"state"=>nil}',
            '{"observed_state"=>{"provider_status"=>"running"}}',
        )
        assert result == {"state": None, "observed_state": {"provider_status": "running"}}


class TestStatusWithProviderStateNilState:
    def _swps(self, status_json: str, provider_state: str) -> dict[str, Any]:
        code = (
            f'include Egame::SDK; '
            f'result = StateMachine.status_with_provider_state({status_json}, "{provider_state}"); '
            f'puts JSON.generate(result)'
        )
        return json.loads(ruby_eval(code))

    def test_nil_state_preserved(self) -> None:
        result = self._swps('{"state"=>nil}', "running")
        assert result == {"state": None}

    def test_missing_state_creates_dict(self) -> None:
        result = self._swps('{}', "running")
        assert result == {"state": {"provider_state": "running"}}


# ---------------------------------------------------------------------------
# Open3.capture3 env-hash form
# ---------------------------------------------------------------------------

class TestOpen3Capture3EnvForm:
    def test_env_overlay_passed_to_subprocess(self) -> None:
        code = (
            'require "open3"; '
            'out, _, _ = Open3.capture3({"_EGAME_TEST_VAR" => "from_overlay"}, '
            '"ruby", "-e", "puts ENV[\\\"_EGAME_TEST_VAR\\\"]"); '
            'puts out.strip'
        )
        assert ruby_eval(code) == "from_overlay"

    def test_empty_env_inherits_parent(self) -> None:
        code = (
            'require "open3"; '
            'out, _, _ = Open3.capture3({}, "ruby", "-e", '
            '"puts ENV.key?(\\\"PATH\\\").to_s"); '
            'puts out.strip'
        )
        assert ruby_eval(code) == "true"
