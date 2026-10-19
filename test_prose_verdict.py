"""Verify terminal prose verdicts without conflating legacy and new runs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core


@pytest.mark.parametrize("body,expected", [
    ("# Report\nDone\nPROFILE_DELEGATE_RESULT: ok", "ok"),
    ("Report\nPROFILE_DELEGATE_RESULT: blocked", "blocked"),
    ("PASS\nDone", "unknown"),
    ("Report\nPROFILE_DELEGATE_RESULT: ok\nTrailing", "unknown"),
    ("Report\nPROFILE_DELEGATE_RESULT: ok\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("```\nPROFILE_DELEGATE_RESULT: ok\n```", "unknown"),
    ("~~~\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("   ~~~~python\n~~~\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("````python\n```\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("~~~\n```\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("~~~python\nexample\n~~~~  \nPROFILE_DELEGATE_RESULT: ok", "ok"),
    ("````python\nexample\n`````\nPROFILE_DELEGATE_RESULT: ok", "ok"),
    ("```invalid`info\nPROFILE_DELEGATE_RESULT: ok", "ok"),
    ("~~~\n~~~ not a closer\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("FAILED\nReport\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
    ("This is not PASS\nPROFILE_DELEGATE_RESULT: ok", "unknown"),
])
def test_new_prose_verdict_contract(body, expected):
    result = core.normalize_result(None, "/tmp/stdout.txt", raw_output=body,
                                   output_mode="markdown", require_terminal_verdict=True)
    assert result["status"] == expected
    assert result["summary"]
    if expected == "unknown":
        assert result["error_code"] == "missing_verdict"
        assert not core.wrapper_success("completed", result)
