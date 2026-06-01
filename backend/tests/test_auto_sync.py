"""Regression tests for the auto-sync change notifier.

`incremental_sync()` returns added/changed/removed as integer *counts* (plus
*_files lists). `_notify_changes` previously indexed those as filename lists
(`changed[:10]`), so any cycle that actually detected changes raised
``'int' object is not subscriptable``. These pin the contract.
"""
import pytest

from app.services.agent.auto_sync import auto_sync


@pytest.fixture(autouse=True)
def _silence_memory(monkeypatch):
    # _notify_changes records to the global memory manager; stub it so the test
    # is hermetic and we're only exercising the shape handling.
    from app.services.agent import memory as mem
    monkeypatch.setattr(mem.memory_manager, "remember", lambda *a, **k: None)


async def test_notify_changes_uses_filename_lists():
    # The real shape incremental_sync returns: counts + *_files lists.
    result = {
        "status": "updated", "changes": 2,
        "added": 1, "changed": 1, "removed": 0,
        "added_files": ["src/new.py"], "changed_files": ["README.md"], "removed_files": [],
    }
    # Must not raise (previously crashed on changed[:10] when changed was an int).
    await auto_sync._notify_changes("repo-x", result)


async def test_notify_changes_tolerates_counts_only():
    # Degenerate/legacy shape with no *_files lists must also not crash.
    await auto_sync._notify_changes("repo-x", {"changes": 1, "added": 0, "changed": 1, "removed": 0})


async def test_notify_changes_noop_when_empty():
    await auto_sync._notify_changes("repo-x", {"status": "up_to_date", "changes": 0})
