import asyncio
import contextlib
import json
import os
import random
import sys
import time
import uuid

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from reaper_mcp_shared.constants import (
    Connection, Timeouts, ensure_private_dir,
    HISTORY_RETENTION_DAYS, HISTORY_PARAM_PREVIEW_CHARS,
)
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

# Heartbeat: lock file must be updated within this many seconds
_HEARTBEAT_STALE_SECONDS = 60

# Diagnostic-only: any command taking longer than this gets a stage-by-stage
# timing breakdown appended to slow_commands.log, so a real slow request from
# a real long-running server can be diagnosed after the fact instead of
# guessed at — isolated fresh-process timing tests can't reproduce whatever
# is different about an already-running, in-use server.
_SLOW_THRESHOLD_SECONDS = 1.0
_SLOW_LOG_FILE = os.path.join(Connection.IPC_DIR, "slow_commands.log")


def _log_slow(command: str, stages: dict) -> None:
    if stages.get("total", 0) < _SLOW_THRESHOLD_SECONDS:
        return
    try:
        ensure_private_dir(Connection.IPC_DIR)
        parts = " ".join(
            f"{k}={v}" if k == "poll_iters" else f"{k}={v:.2f}s"
            for k, v in stages.items()
        )
        with open(_SLOW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} "
                    f"cmd={command} {parts}\n")
    except OSError:
        pass


# Chance of running the retention sweep on any given archived command, so a
# long-running server (days/weeks without a restart) still cleans up
# eventually without needing a dedicated timer thread. Startup also sweeps
# once unconditionally — see ReaperClient.__init__.
_SWEEP_PROBABILITY = 1.0 / 200


def _sweep_history(max_age_days: float = HISTORY_RETENTION_DAYS) -> None:
    """Delete archived command entries older than max_age_days.

    Pass or fail, no distinction — retention is purely about age, matching
    what was asked for: keep everything for review, then let it go after 30
    days regardless of outcome.
    """
    try:
        cutoff = time.time() - max_age_days * 86400
        with os.scandir(Connection.HISTORY_DIR) as it:
            for entry in it:
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        os.remove(entry.path)
                except OSError:
                    continue  # another process may have already removed it
    except FileNotFoundError:
        pass  # nothing archived yet — nothing to sweep
    except Exception:
        pass  # best-effort cleanup — never let this disrupt a real command


def _archive_command(command: str, params: dict, success: bool, detail, duration: float) -> None:
    """Write one record of a completed command for after-the-fact review.

    command.json/response.json are deleted immediately after each
    round-trip, so without this there's no record of what was sent once
    it's done — exactly the gap that made today's crash investigation rely
    entirely on REAPER's own minidumps instead of anything reaper-mcp
    itself kept. Best-effort: a failure here must never take down the
    actual command it's archiving.
    """
    try:
        ensure_private_dir(Connection.HISTORY_DIR)
        params_json = json.dumps(params, default=str)
        truncated = len(params_json) > HISTORY_PARAM_PREVIEW_CHARS
        if truncated:
            params_json = params_json[:HISTORY_PARAM_PREVIEW_CHARS]
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pid": os.getpid(),
            "command": command,
            "params_preview": params_json,
            "params_truncated": truncated,
            "success": success,
            "duration_sec": round(duration, 3),
        }
        if success:
            record["result_preview"] = json.dumps(detail, default=str)[:HISTORY_PARAM_PREVIEW_CHARS]
        else:
            record["error"] = str(detail)

        # Sortable-by-name filename doubles as a unique ID without needing
        # to read the file first — matches the "unique identifier + timestamp"
        # shape asked for.
        fname = f"{time.time():.6f}_{record['id'][:8]}.json"
        path = os.path.join(Connection.HISTORY_DIR, fname)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(tmp, path)

        if random.random() < _SWEEP_PROBABILITY:
            _sweep_history()
    except Exception:
        # Deliberately broad, not just OSError — this is a best-effort
        # telemetry path, and *anything* going wrong here (a bad path, a
        # json.dumps edge case, whatever) must never take down the real
        # command it's archiving. Confirmed by test: a null-byte path
        # raises ValueError, not OSError, so OSError alone wasn't enough.
        pass


@contextlib.contextmanager
def _ipc_mutex(timeout: float):
    """Real OS-level mutual exclusion for one full command round-trip.

    This is what actually prevents cross-talk when more than one reaper-mcp
    server process is alive at once (e.g. two separate Claude clients each
    running their own server against the same shared IPC files) — a real
    lock means the second process just waits its turn instead of racing on
    command.json/response.json, or being killed outright. Non-blocking
    polling loop (not a blocking OS wait) so we can respect the caller's
    timeout budget and raise a normal ReaperMCPError instead of hanging.
    """
    ensure_private_dir(Connection.IPC_DIR)
    fd = open(Connection.IPC_MUTEX_FILE, "a+b")
    try:
        fd.seek(0, os.SEEK_END)
        if fd.tell() == 0:
            fd.write(b"\0")
            fd.flush()

        deadline = time.monotonic() + timeout
        while True:
            fd.seek(0)
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ReaperMCPError(
                        ErrorCode.COMMAND_TIMEOUT,
                        "Timed out waiting for another in-flight REAPER command "
                        "(from this or another reaper-mcp server) to finish.",
                    )
                time.sleep(Timeouts.POLL_INTERVAL)

        try:
            yield
        finally:
            fd.seek(0)
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        fd.close()


def _is_wsl() -> bool:
    """True if this Python process is running inside WSL (not native Windows).

    Matters because REAPER itself always runs as a native Windows .exe — WSL
    has no GUI app support for a full DAW — so if the *Python* side is
    launched from inside WSL instead of native Windows Python,
    tempfile.gettempdir() resolves to WSL's own /tmp (a separate ext4
    filesystem inside the WSL VM), never the real %TEMP% REAPER's Lua side
    writes IPC files to. The two sides silently never see each other's
    files — every command times out with no indication why.
    """
    if sys.platform != "linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


class ReaperClient:
    def __init__(self):
        self._lock = asyncio.Lock()
        ensure_private_dir(Connection.IPC_DIR)
        _sweep_history()  # unconditional at startup — catches long-running
                          # servers between the probabilistic per-command sweeps

    def _check_server(self):
        if not os.path.exists(Connection.LOCK_FILE):
            if _is_wsl():
                raise ReaperMCPError(
                    ErrorCode.CONNECTION_REFUSED,
                    f"REAPER MCP server not running — but also: this Python process "
                    f"is running INSIDE WSL, looking for IPC files at {Connection.IPC_DIR} "
                    f"(WSL's own filesystem). REAPER itself always runs as a native "
                    f"Windows app and writes its IPC files to Windows' %TEMP%, a "
                    f"completely different filesystem — the two sides can never see "
                    f"each other's files this way, even with REAPER and the Lua "
                    f"script both actually running. Run this Python server as native "
                    f"Windows Python instead (not from inside a WSL shell) — e.g. "
                    f"point Claude Desktop's config at the Windows python.exe / "
                    f"reaper-mcp.exe, not the WSL one.",
                )
            raise ReaperMCPError(
                ErrorCode.CONNECTION_REFUSED,
                "REAPER MCP server not running. "
                "In REAPER: Actions > Show action list > Load ReaScript > reaper_mcp_server.lua > Run",
            )
        # Check heartbeat — if lock file is stale, server likely crashed
        if self._heartbeat_stale():
            raise ReaperMCPError(
                ErrorCode.CONNECTION_LOST,
                "REAPER MCP server appears stale (no heartbeat). "
                "Re-run the Lua script in REAPER.",
            )

    def _heartbeat_stale(self) -> bool:
        """True if the Lua side's heartbeat hasn't updated recently.

        The Lua bridge refreshes server.lock's mtime every HEARTBEAT_INTERVAL
        (10s) from its main defer loop. A crash doesn't delete that file — it
        just stops updating it — so staleness, not existence, is the actual
        crash signal. Existence-only checks (the bug this replaced) never
        fire on a real crash, since the stale file just sits there looking
        "present" for as long as nothing else cleans it up.
        """
        try:
            return time.time() - os.path.getmtime(Connection.LOCK_FILE) > _HEARTBEAT_STALE_SECONDS
        except OSError:
            return False  # can't tell — don't report a crash we haven't confirmed

    def _cleanup_files(self):
        for f in (Connection.COMMAND_FILE, Connection.RESPONSE_FILE,
                  Connection.COMMAND_TMP, Connection.RESPONSE_TMP):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
            except OSError:
                # PermissionError / locked file on Windows (antivirus, indexer, etc.).
                # Not fatal — the next command will rename over stale files anyway.
                pass

    def _send_command(self, command: str, timeout: float, **params) -> dict:
        t_start = time.monotonic()
        try:
            self._check_server()
            t_checked = time.monotonic()
            with _ipc_mutex(timeout):
                t_locked = time.monotonic()
                result, inner_stages = self._send_command_locked(command, timeout, **params)
                t_done = time.monotonic()
            stages = {
                "check_server": t_checked - t_start,
                "mutex_wait": t_locked - t_checked,
                **inner_stages,
                "total": t_done - t_start,
            }
            _log_slow(command, stages)
            _archive_command(command, params, True, result, stages["total"])
            return result
        except Exception as exc:
            _archive_command(command, params, False, exc, time.monotonic() - t_start)
            raise

    def _send_command_locked(self, command: str, timeout: float, **params) -> tuple[dict, dict]:
        t0 = time.monotonic()
        self._cleanup_files()
        t1 = time.monotonic()

        # Write command atomically
        msg = json.dumps({"command": command, "params": params})
        with open(Connection.COMMAND_TMP, "w", encoding="utf-8") as f:
            f.write(msg)
        os.replace(Connection.COMMAND_TMP, Connection.COMMAND_FILE)
        t2 = time.monotonic()

        # Poll for response. On parse failure we require the response file's
        # mtime to CHANGE before retrying — otherwise we're re-reading the
        # same truncated bytes and will always fail 3 times in a row even
        # when the real response is on its way.
        deadline = time.monotonic() + timeout
        parse_failures = 0
        max_parse_failures = 3
        last_parse_fail_mtime: float | None = None
        poll_count = 0
        while time.monotonic() < deadline:
            if os.path.exists(Connection.RESPONSE_FILE):
                try:
                    current_mtime = os.path.getmtime(Connection.RESPONSE_FILE)
                    # If the file hasn't been updated since our last parse
                    # failure, don't count another failure — just wait.
                    if last_parse_fail_mtime is not None and current_mtime <= last_parse_fail_mtime:
                        time.sleep(Timeouts.POLL_INTERVAL)
                        continue
                    with open(Connection.RESPONSE_FILE, "r", encoding="utf-8") as f:
                        raw = f.read()
                    if raw.strip():
                        try:
                            result = json.loads(raw)
                            try:
                                os.remove(Connection.RESPONSE_FILE)
                            except OSError:
                                pass
                            return result, {
                                "cleanup": t1 - t0,
                                "write": t2 - t1,
                                "poll": time.monotonic() - t2,
                                "poll_iters": poll_count,
                            }
                        except (json.JSONDecodeError, UnicodeDecodeError) as dec_err:
                            parse_failures += 1
                            last_parse_fail_mtime = current_mtime
                            if parse_failures >= max_parse_failures:
                                try:
                                    os.remove(Connection.RESPONSE_FILE)
                                except OSError:
                                    pass
                                raise ReaperMCPError(
                                    ErrorCode.COMMAND_FAILED,
                                    f"Malformed response from REAPER after "
                                    f"{parse_failures} attempts — check REAPER "
                                    f"console for Lua errors. Detail: {dec_err}",
                                )
                            time.sleep(Timeouts.POLL_INTERVAL)
                            continue
                except OSError:
                    pass
                except UnicodeDecodeError as dec_err:
                    # File exists but isn't valid UTF-8 yet — probably mid-write.
                    parse_failures += 1
                    if parse_failures >= max_parse_failures:
                        raise ReaperMCPError(
                            ErrorCode.COMMAND_FAILED,
                            f"Response file isn't valid UTF-8 after "
                            f"{parse_failures} attempts: {dec_err}",
                        )
                    time.sleep(Timeouts.POLL_INTERVAL)
                    continue
            # Check for REAPER crash every ~2 seconds during polling. Staleness,
            # not existence — see _heartbeat_stale(). This is what lets a crash
            # mid-command surface in ~heartbeat-stale-seconds instead of the
            # full command timeout (up to 600s for execute_long).
            poll_count += 1
            if poll_count % 40 == 0 and self._heartbeat_stale():
                raise ReaperMCPError(ErrorCode.CONNECTION_LOST, "REAPER MCP server stopped during command")
            time.sleep(Timeouts.POLL_INTERVAL)

        if self._heartbeat_stale():
            raise ReaperMCPError(ErrorCode.CONNECTION_LOST, "REAPER MCP server stopped")
        raise ReaperMCPError(ErrorCode.COMMAND_TIMEOUT, f"Command '{command}' timed out after {timeout}s")

    async def execute(self, command: str, **params) -> dict:
        try:
            async with self._lock:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self._send_command(command, Timeouts.COMMAND, **params)),
                    timeout=Timeouts.COMMAND + 5,
                )
        except asyncio.TimeoutError:
            raise ReaperMCPError(ErrorCode.COMMAND_TIMEOUT, f"Command '{command}' timed out")
        if not result.get("success", False):
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, result.get("error", "Unknown error"))
        return result

    async def execute_long(self, command: str, **params) -> dict:
        try:
            async with self._lock:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self._send_command(command, Timeouts.LONG_COMMAND, **params)),
                    timeout=Timeouts.LONG_COMMAND + 5,
                )
        except asyncio.TimeoutError:
            raise ReaperMCPError(ErrorCode.COMMAND_TIMEOUT, f"Command '{command}' timed out")
        if not result.get("success", False):
            raise ReaperMCPError(ErrorCode.COMMAND_FAILED, result.get("error", "Unknown error"))
        return result

    async def close(self):
        pass
