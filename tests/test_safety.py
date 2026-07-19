"""Tests for reaper_mcp/safety.py — the auto-backup safety net.

Uses a minimal fake client (no real REAPER/IPC dependency) since the logic
here is pure decision-making: given project_get_info's response, should a
backup happen, and does a failure in either call ever propagate instead of
being swallowed.
"""

import pytest

import reaper_mcp.safety as safety


class FakeClient:
    """Records calls and returns canned responses per command name."""

    def __init__(self, responses=None, raise_on=None):
        self.responses = responses or {}
        self.raise_on = raise_on or set()
        self.calls = []

    async def execute(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command in self.raise_on:
            raise RuntimeError(f"simulated failure for {command}")
        return self.responses.get(command, {})


@pytest.fixture(autouse=True)
def reset_backup_state():
    """The 'already backed up this session' set is module-level — isolate tests."""
    safety._backed_up_this_session.clear()
    yield
    safety._backed_up_this_session.clear()


class TestEnsureBackup:
    @pytest.mark.asyncio
    async def test_no_file_path_skips_backup(self):
        client = FakeClient(responses={
            "project_get_info": {"file_path": "", "track_count": 3, "item_count": 5},
        })
        result = await safety.ensure_backup(client)
        assert result is None
        assert not any(cmd == "project_backup" for cmd, _ in client.calls)

    @pytest.mark.asyncio
    async def test_empty_project_skips_backup(self):
        client = FakeClient(responses={
            "project_get_info": {"file_path": "C:\\proj\\song.rpp", "track_count": 0, "item_count": 0},
        })
        result = await safety.ensure_backup(client)
        assert result is None
        assert not any(cmd == "project_backup" for cmd, _ in client.calls)

    @pytest.mark.asyncio
    async def test_saved_nonempty_project_triggers_backup(self):
        client = FakeClient(responses={
            "project_get_info": {"file_path": "C:\\proj\\song.rpp", "track_count": 3, "item_count": 5},
            "project_backup": {"path": "whatever", "saved": True},
        })
        result = await safety.ensure_backup(client)
        assert result is not None
        assert "backup_path" in result
        backup_calls = [kwargs for cmd, kwargs in client.calls if cmd == "project_backup"]
        assert len(backup_calls) == 1
        assert backup_calls[0]["path"].startswith("C:\\proj\\song.mcp-backup-")
        assert backup_calls[0]["path"].endswith(".rpp")

    @pytest.mark.asyncio
    async def test_second_call_same_project_is_noop(self):
        client = FakeClient(responses={
            "project_get_info": {"file_path": "C:\\proj\\song.rpp", "track_count": 3, "item_count": 5},
            "project_backup": {"path": "whatever", "saved": True},
        })
        first = await safety.ensure_backup(client)
        second = await safety.ensure_backup(client)
        assert first is not None
        assert second is None
        backup_calls = [c for c in client.calls if c[0] == "project_backup"]
        assert len(backup_calls) == 1  # not called again

    @pytest.mark.asyncio
    async def test_different_projects_each_get_a_backup(self):
        client_a = FakeClient(responses={
            "project_get_info": {"file_path": "C:\\proj\\a.rpp", "track_count": 1, "item_count": 1},
            "project_backup": {"saved": True},
        })
        client_b = FakeClient(responses={
            "project_get_info": {"file_path": "C:\\proj\\b.rpp", "track_count": 1, "item_count": 1},
            "project_backup": {"saved": True},
        })
        result_a = await safety.ensure_backup(client_a)
        result_b = await safety.ensure_backup(client_b)
        assert result_a is not None
        assert result_b is not None

    @pytest.mark.asyncio
    async def test_project_get_info_failure_does_not_raise(self):
        client = FakeClient(raise_on={"project_get_info"})
        result = await safety.ensure_backup(client)
        assert result is None

    @pytest.mark.asyncio
    async def test_project_backup_failure_does_not_raise(self):
        client = FakeClient(
            responses={
                "project_get_info": {"file_path": "C:\\proj\\song.rpp", "track_count": 1, "item_count": 1},
            },
            raise_on={"project_backup"},
        )
        result = await safety.ensure_backup(client)
        assert result is None
