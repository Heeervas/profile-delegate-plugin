"""Regression coverage for the plugin-only reliability reset."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
FIXTURES = PLUGIN_DIR / "tests" / "fixtures" / "profile_delegate"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import core


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def normalized_fixture(name: str, *, output_mode: str = "json") -> dict:
    raw = fixture_text(name)
    parsed, meta = core.parse_json_result(raw)
    return core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
        output_mode=output_mode,
    )


def test_repository_fixtures_are_portable_and_immutable_inputs():
    assert FIXTURES.is_dir()
    runtime_prefix = "/opt/data/profile_delegate" + "/runs"
    assert runtime_prefix not in Path(__file__).read_text(encoding="utf-8")
    assert all(path.is_file() for path in FIXTURES.iterdir())


def test_historical_custom_json_contracts_remain_structured():
    blocked = normalized_fixture("historical_custom_blocked.json")
    assert blocked["status"] == "blocked"
    assert blocked["structured"] is True
    assert blocked["contract_status"] == "valid"
    assert blocked["modified_files"] == []

    ok = normalized_fixture("historical_custom_ok.json")
    assert ok["status"] == "ok"
    assert ok["structured"] is True
    assert ok["contract_status"] == "valid"
    assert ok["artifacts_changed"]


def test_historical_markdown_blocked_report_is_recovered_not_false_green():
    result = normalized_fixture("historical_markdown_blocked.md")
    assert result["status"] == "blocked"
    assert result["execution_status"] == "completed"
    assert result["contract_status"] == "recovered"
    assert result["structured"] is False
    assert result["raw_output_path"] == "/tmp/stdout.txt"
    assert core.wrapper_success("completed", result) is False


def test_historical_markdown_only_contract_and_full_markdown_compatibility():
    request = json.loads(fixture_text("historical_markdown_request.json"))
    requested, resolved = core.resolve_output_mode("auto", request["output_contract"])
    assert (requested, resolved) == ("auto", "markdown")
    result = normalized_fixture("historical_markdown_plan.md", output_mode=resolved)
    assert result["status"] == "unknown"
    assert result["contract_status"] == "drifted"
    assert result.get("error_code") != "unstructured_output"

    assert core.resolve_output_mode("auto", "Full Markdown") == ("auto", "markdown")


def test_historical_warning_prefixed_custom_json_stays_useful_unknown():
    result = normalized_fixture("historical_warning_custom.txt")
    assert result["status"] == "unknown"
    assert result["structured"] is True
    assert result["contract_status"] == "recovered"
    assert result["raw_output_path"] == "/tmp/stdout.txt"
    assert result["verdict"] == "PASS"
    assert core.wrapper_success("completed", result) is False


def test_historical_plain_text_exact_line_remains_useful_unknown():
    result = normalized_fixture("historical_plain_text.txt", output_mode="text")
    assert result["status"] == "unknown"
    assert result["contract_status"] == "drifted"
    assert "COACH_V2_CONTRACT_OK" in fixture_text("historical_plain_text.txt")
    assert "error_code" not in result
    assert core.wrapper_success("completed", result) is False


@pytest.mark.parametrize(
    "raw",
    [
        "Verdict: not OK — BLOCKED",
        "Verdict: OK / BLOCKED",
        "Verdict: FAILED, then OK",
        "STATUS: not failed",
        "OK but BLOCKED",
        "OK\nVerdict: not BLOCKED",
        "Status: OK\nThis is never FAILED",
    ],
)
def test_text_status_grammar_rejects_negated_or_multiple_statuses(raw: str):
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output=raw, output_mode="text")
    assert result["status"] == "unknown"
    assert result["contract_status"] == "drifted"
    assert core.wrapper_success("completed", result) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("OK", "ok"),
        ("OK_WITH_EVIDENCE", "ok"),
        ("## `BLOCKED_NEEDS_FIXES`", "blocked"),
        ("Verdict: FAILED", "failed"),
        ("Status: blocked", "blocked"),
    ],
)
def test_text_status_grammar_accepts_one_explicit_status(raw: str, expected: str):
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output=raw, output_mode="text")
    assert result["status"] == expected


def test_ambiguous_json_with_leading_ok_can_never_recover_success():
    raw = (
        "OK\n"
        '{"status":"ok","summary":"one"}\n'
        '{"status":"blocked","summary":"two"}'
    )
    parsed, meta = core.parse_json_result(raw)
    result = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
    )
    assert result["status"] == "unknown"
    assert result["parse_error"] == "ambiguous_json_candidates"
    assert result["contract_status"] == "drifted"
    assert core.wrapper_success("completed", result) is False


def test_any_parse_error_overrides_a_caller_supplied_ok_object():
    result = core.normalize_result(
        {"status": "ok", "summary": "must not win"},
        "/tmp/stdout.txt",
        raw_output="OK",
        parse_meta={
            "parse_method": "ambiguous",
            "candidate_count": 2,
            "selected_span": None,
            "parse_error": "ambiguous_json_candidates",
        },
    )
    assert result["status"] == "unknown"
    assert result["contract_status"] == "drifted"
    assert core.wrapper_success("completed", result) is False


def test_malformed_outer_json_cannot_promote_a_nested_ok_object():
    raw = 'prefix {"data": INVALID, "nested":{"status":"ok","summary":"done"}}'
    parsed, meta = core.parse_json_result(raw)
    result = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
    )
    assert parsed is None
    assert result["status"] == "unknown"
    assert result["contract_status"] == "drifted"
    assert core.wrapper_success("completed", result) is False


def test_whole_json_is_valid_but_fenced_and_embedded_json_are_recovered():
    whole = '{"status":"ok","summary":"done"}'
    fenced = f"```json\n{whole}\n```"
    embedded = f"warning\n{whole}"
    for raw, expected_contract in [
        (whole, "valid"), (fenced, "recovered"), (embedded, "recovered"),
    ]:
        parsed, meta = core.parse_json_result(raw)
        result = core.normalize_result(
            parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
        )
        assert result["contract_status"] == expected_contract
        assert ("raw_output_path" in result) is (expected_contract == "recovered")


def test_whole_statusless_custom_json_is_valid_but_task_outcome_is_unknown():
    raw = '{"verdict":"PASS","findings":[]}'
    parsed, meta = core.parse_json_result(raw)
    result = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
    )
    assert result["status"] == "unknown"
    assert result["contract_status"] == "valid"
    assert "raw_output_path" not in result
    assert core.wrapper_success("completed", result) is False


@pytest.mark.parametrize(
    ("requested", "contract", "resolved"),
    [
        ("auto", "", "json"),
        ("auto", "JSON only", "json"),
        ("auto", "Return full Markdown plan only", "markdown"),
        ("auto", "Full Markdown", "markdown"),
        ("auto", "Plain text only", "text"),
        ("json", "", "json"),
        ("markdown", "", "markdown"),
        ("text", "", "text"),
        ("json", "JSON only", "json"),
        ("markdown", "Markdown only", "markdown"),
        ("text", "Plain text only", "text"),
    ],
)
def test_output_mode_intent_matrix_accepts_compatible_combinations(
    requested: str, contract: str, resolved: str,
):
    assert core.resolve_output_mode(requested, contract) == (requested, resolved)


@pytest.mark.parametrize(
    ("requested", "contract"),
    [
        ("json", "Markdown only"),
        ("json", "Plain text only"),
        ("markdown", "JSON only"),
        ("markdown", "Plain text only"),
        ("text", "JSON only"),
        ("text", "Markdown only"),
        ("auto", "JSON only; Markdown only"),
        ("auto", "Plain text only; JSON only"),
    ],
)
def test_output_mode_intent_matrix_rejects_conflicts(requested: str, contract: str):
    with pytest.raises(core.ProfileDelegateError) as caught:
        core.resolve_output_mode(requested, contract)
    assert caught.value.code == "contract_conflict"


@pytest.mark.parametrize(
    ("execution_status", "task_status", "contract_status", "expected"),
    [
        ("completed", "ok", "valid", True),
        ("completed", "ok", "recovered", True),
        ("completed", "blocked", "valid", False),
        ("completed", "failed", "valid", False),
        ("completed", "unknown", "drifted", False),
        ("failed", "ok", "valid", False),
        ("cancelled", "ok", "valid", False),
        ("timed_out", "ok", "valid", False),
        ("completed", "ok", "drifted", False),
    ],
)
def test_wrapper_success_is_orthogonal_and_authoritative(
    execution_status: str, task_status: str, contract_status: str, expected: bool,
):
    result = {
        "status": task_status,
        "execution_status": execution_status,
        "contract_status": contract_status,
    }
    assert core.wrapper_success(execution_status, result) is expected


def test_malformed_json_candidate_blocks_textual_ok_recovery():
    raw = 'OK\n{"status":"blocked","summary":"truncated"'
    parsed, meta = core.parse_json_result(raw)
    assert parsed is None
    assert meta["parse_error"] == "malformed_json_candidate"
    result = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta,
    )
    assert result["status"] == "unknown"
    assert result["error_code"] == "malformed_json_candidate"
    assert core.wrapper_success("completed", result) is False


def test_text_status_recovery_scans_full_bounded_output_for_conflicts():
    raw = "OK\n" + "\n".join(f"detail {index}" for index in range(35)) + "\nSTATUS: BLOCKED"
    parsed, meta = core.parse_json_result(raw)
    result = core.normalize_result(
        parsed, "/tmp/stdout.txt", raw_output=raw, parse_meta=meta, output_mode="text",
    )
    assert result["status"] == "unknown"
    assert core.wrapper_success("completed", result) is False


@pytest.mark.parametrize(
    "contract",
    [
        "Markdown only; Plain text only",
        "JSON only; Markdown only; Plain text only",
    ],
)
def test_auto_output_mode_rejects_remaining_multi_intent_conflicts(contract: str):
    with pytest.raises(core.ProfileDelegateError) as caught:
        core.resolve_output_mode("auto", contract)
    assert caught.value.code == "contract_conflict"
