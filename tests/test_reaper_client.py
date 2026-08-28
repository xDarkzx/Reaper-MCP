"""Tests for ReaperClient's heartbeat-staleness crash detection and
request/response id correlation.

Pure logic — no REAPER/IPC needed.
"""

import os
import time

from reaper_mcp.reaper_client import ReaperClient, _is_stale_response
from reaper_mcp_shared.constants import Connection


class TestHeartbeatStale:
    def test_fresh_lock_file_not_stale(self, tmp_path, monkeypatch):
        lock_file = tmp_path / "server.lock"
        lock_file.write_text("1")
        monkeypatch.setattr(Connection, "LOCK_FILE", str(lock_file))

        client = ReaperClient.__new__(ReaperClient)  # skip __init__'s dir setup
        assert client._heartbeat_stale() is False

    def test_old_lock_file_is_stale(self, tmp_path, monkeypatch):
        lock_file = tmp_path / "server.lock"
        lock_file.write_text("1")
        old_time = time.time() - 120  # older than _HEARTBEAT_STALE_SECONDS (60)
        os.utime(lock_file, (old_time, old_time))
        monkeypatch.setattr(Connection, "LOCK_FILE", str(lock_file))

        client = ReaperClient.__new__(ReaperClient)
        assert client._heartbeat_stale() is True

    def test_missing_lock_file_is_not_reported_as_stale(self, tmp_path, monkeypatch):
        """A missing file is a different failure mode (server never started),
        handled separately by _check_server's existence check — staleness
        can't be determined without a file to read mtime from, so this must
        fail open (False) rather than claim staleness it can't confirm."""
        missing = tmp_path / "does-not-exist.lock"
        monkeypatch.setattr(Connection, "LOCK_FILE", str(missing))

        client = ReaperClient.__new__(ReaperClient)
        assert client._heartbeat_stale() is False

    def test_boundary_just_under_threshold_not_stale(self, tmp_path, monkeypatch):
        lock_file = tmp_path / "server.lock"
        lock_file.write_text("1")
        recent = time.time() - 30  # well under the 60s threshold
        os.utime(lock_file, (recent, recent))
        monkeypatch.setattr(Connection, "LOCK_FILE", str(lock_file))

        client = ReaperClient.__new__(ReaperClient)
        assert client._heartbeat_stale() is False


class TestIsStaleResponse:
    def test_matching_id_is_not_stale(self):
        assert _is_stale_response("abc123", "abc123") is False

    def test_mismatched_id_is_stale(self):
        # The actual bug this fixes: a late response from a command this
        # client already gave up on must not be accepted as the answer to
        # a different, currently in-flight command.
        assert _is_stale_response("old-command-id", "new-command-id") is True

    def test_response_with_no_id_is_not_stale(self):
        # Backward compat: an old, not-yet-reloaded Lua bridge never sends
        # an id at all. Must be accepted, not discarded forever.
        assert _is_stale_response(None, "new-command-id") is False
