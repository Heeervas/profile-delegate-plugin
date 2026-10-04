"""Fixture commands must remain flagged yet eligible for native exact grants."""
import importlib.util
from pathlib import Path

import pytest



def test_runtime_fixture_command_is_flagged_and_not_compound(tmp_path, monkeypatch):
    from tools.approval_detection import detect_dangerous_command
    from tools.approval_floors import _has_allowlist_shell_operator
    spec = importlib.util.spec_from_file_location(
        "runtime_fixture_commands", Path(__file__).parents[1] / "scripts" / "accept_task_approval_runtime.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    marker = tmp_path / "target-grant.txt"
    action = module.terminal_action(marker)
    command = action["arguments"]["command"]
    assert command == "python3 -c 'import acceptance_target_grant'"
    dangerous, _, _ = detect_dangerous_command(command)
    assert dangerous is True
    benign, _, _ = detect_dangerous_command("pwd")
    assert benign is False
    assert not _has_allowlist_shell_operator(command)
    from tools import approval
    from tools.approval_floors import _command_matches_permanent_allowlist
    monkeypatch.setattr(approval, "_permanent_set", lambda: {command})
    assert _command_matches_permanent_allowlist(command)
    assert (tmp_path / "acceptance_target_grant.py").is_file()
    assert not marker.exists()  # preparation does not execute the marker operation
    old = "python3 -c 'from pathlib import Path; Path(\"marker\").write_text(\"x\")'"
    assert _has_allowlist_shell_operator(old)


def test_false_detector_tuple_is_detected(tmp_path, monkeypatch):
    from tools import approval_detection
    monkeypatch.setattr(approval_detection, 'detect_dangerous_command', lambda command: (False, None, None))
    with pytest.raises(AssertionError):
        test_runtime_fixture_command_is_flagged_and_not_compound(tmp_path, monkeypatch)
