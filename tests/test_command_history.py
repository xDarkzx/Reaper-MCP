"""Tests for the command-history archive (reaper_mcp/reaper_client.py).

command.json/response.json get deleted immediately after each round-trip,
so without this there's no record of what was sent once a command
completes — this fills that gap with a small JSON file per command, swept
after 30 days regardless of pass/fail.

Pure filesystem logic against a real temp dir — no REAPER/IPC needed.
"""

import glob
import json
import os
import time

import pytest

from reaper_mcp_shared.constants import Connection
import reaper_mcp.reaper_client as rc


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Connection, "IPC_DIR", str(tmp_path))
    monkeypatch.setattr(Connection, "HISTORY_DIR", str(tmp_path / "history"))
    return Connection.HISTORY_DIR


class TestArchiveCommand:
    def test_successful_command_creates_one_file(self, history_dir):
        rc._archive_command("track_get_all", {}, True, {"tracks": []}, 0.123)
        files = os.listdir(history_dir)
        assert len(files) == 1

    def test_record_contains_expected_fields(self, history_dir):
        rc._archive_command("track_get_all", {"track_index": 0}, True, {"ok": True}, 0.5)
        path = os.path.join(history_dir, os.listdir(history_dir)[0])
        with open(path) as f:
            record = json.load(f)
        assert record["command"] == "track_get_all"
        assert record["success"] is True
        assert record["duration_sec"] == 0.5
        assert "id" in record and "timestamp" in record and "pid" in record
        assert "result_preview" in record
        assert "error" not in record

    def test_failed_command_records_error_not_result(self, history_dir):
        rc._archive_command("fx_add", {"track_index": 0}, False, RuntimeError("boom"), 0.05)
        path = os.path.join(history_dir, os.listdir(history_dir)[0])
        with open(path) as f:
            record = json.load(f)
        assert record["success"] is False
        assert record["error"] == "boom"
        assert "result_preview" not in record

    def test_huge_params_get_truncated(self, history_dir):
        big_params = {"notes": list(range(100000))}
        rc._archive_command("midi_insert_notes_batch", big_params, True, {"ok": True}, 1.0)
        path = os.path.join(history_dir, os.listdir(history_dir)[0])
        with open(path) as f:
            record = json.load(f)
        assert record["params_truncated"] is True
        assert len(record["params_preview"]) <= 2000

    def test_small_params_not_flagged_truncated(self, history_dir):
        rc._archive_command("track_rename", {"track_index": 0, "name": "Kick"}, True, {}, 0.01)
        path = os.path.join(history_dir, os.listdir(history_dir)[0])
        with open(path) as f:
            record = json.load(f)
        assert record["params_truncated"] is False

    def test_each_call_gets_a_unique_file(self, history_dir):
        for _ in range(5):
            rc._archive_command("transport_play", {}, True, {}, 0.01)
        assert len(os.listdir(history_dir)) == 5

    def test_archiving_failure_does_not_raise(self, history_dir, monkeypatch):
        """Best-effort: a broken history dir must never take down the
        actual command it's trying to archive."""
        monkeypatch.setattr(Connection, "HISTORY_DIR", "\0invalid")
        rc._archive_command("transport_play", {}, True, {}, 0.01)  # must not raise


class TestSweepHistory:
    def test_old_entries_removed_fresh_entries_kept(self, history_dir):
        rc._archive_command("old_one", {}, True, {}, 0.1)
        rc._archive_command("fresh_one", {}, True, {}, 0.1)
        paths = sorted(glob.glob(os.path.join(history_dir, "*.json")))
        assert len(paths) == 2

        old_time = time.time() - 40 * 86400  # older than the 30-day retention window
        os.utime(paths[0], (old_time, old_time))

        rc._sweep_history()
        remaining = os.listdir(history_dir)
        assert len(remaining) == 1

    def test_sweep_on_missing_dir_is_a_noop(self, history_dir):
        rc._sweep_history()  # dir doesn't exist yet — must not raise

    def test_sweep_respects_custom_max_age(self, history_dir):
        rc._archive_command("something", {}, True, {}, 0.1)
        path = glob.glob(os.path.join(history_dir, "*.json"))[0]
        five_days_ago = time.time() - 5 * 86400
        os.utime(path, (five_days_ago, five_days_ago))

        rc._sweep_history(max_age_days=30)
        assert len(os.listdir(history_dir)) == 1  # newer than 30 days, survives

        rc._sweep_history(max_age_days=1)
        assert len(os.listdir(history_dir)) == 0  # older than 1 day, removed
