"""Do not import the invoking repair run's ancestry into disposable test fixtures.

Tests exercising ancestry explicitly install their own request after this fixture.
This affects pytest fixtures only, never the running agent or production envelope.
"""
import os
from pathlib import Path

import pytest

# Conservative module partition: these modules exercise native configuration,
# SessionDB/ledger, display/contracts or transitive admission in mixed tests.
# Every case remains in the mandatory installed job; no nodeid exception list.
RUNTIME_MODULES = {
    "test_compression_continuity", "test_native_approval", "test_native_detached_fixture",
    "test_native_resume_admission", "test_native_selection", "test_package_loading",
    "test_preflight_contract", "test_profile_delegate", "test_recursion_integration",
    "test_reliability_20260927", "test_runtime_fixture_commands", "test_sync_lifecycle",
    "test_task_approval_selection", "test_tui_rpc",
}


def pytest_collection_modifyitems(items):
    for item in items:
        if Path(str(item.path)).stem in RUNTIME_MODULES:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def native_runtime_checked():
    from scripts.native_prerequisite import check_runtime
    return check_runtime(Path(os.environ.get("PROFILE_DELEGATE_TEST_RUNTIME", "/opt/hermes")))


@pytest.fixture(autouse=True)
def installed_runtime_prerequisite(request):
    if request.node.get_closest_marker("integration"):
        request.getfixturevalue("native_runtime_checked")



@pytest.fixture(autouse=True)
def isolated_delegation_lineage(monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
