"""Do not import the invoking repair run's ancestry into disposable test fixtures.

Tests exercising ancestry explicitly install their own request after this fixture.
This affects pytest fixtures only, never the running agent or production envelope.
"""
import pytest


@pytest.fixture(autouse=True)
def isolated_delegation_lineage(monkeypatch):
    monkeypatch.delenv("PROFILE_DELEGATE_APPROVAL_REQUEST", raising=False)
    monkeypatch.delenv("PROFILE_DELEGATE_PARENT_TASK_ID", raising=False)
