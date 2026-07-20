import asyncio
import contextlib
import json
import os
import sys
import time

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from reaper_mcp_shared.constants import Connection, Timeouts
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
        os.makedirs(Connection.IPC_DIR, exist_ok=True)
        parts = " ".join(
            f"{k}={v}" if k == "poll_iters" else f"{k}={v:.2f}s"
            for k, v in stages.items()
        )
        with open(_SLOW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} "
                    f"cmd={command} {parts}\n")
    except OSError:
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
    os.makedirs(Connection.IPC_DIR, exist_ok=True)
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
        os.makedirs(Connection.IPC_DIR, exist_ok=True)

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
        try:
            mtime = os.path.getmtime(Connection.LOCK_FILE)
            if time.time() - mtime > _HEARTBEAT_STALE_SECONDS:
                raise ReaperMCPError(
                    ErrorCode.CONNECTION_LOST,
                    "REAPER MCP server appears stale (no heartbeat). "
                    "Re-run the Lua script in REAPER.",
                )
        except OSError:
            pass

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
        return result

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
            # Check for REAPER crash every ~2 seconds during polling
            poll_count += 1
            if poll_count % 40 == 0 and not os.path.exists(Connection.LOCK_FILE):
                raise ReaperMCPError(ErrorCode.CONNECTION_LOST, "REAPER MCP server stopped during command")
            time.sleep(Timeouts.POLL_INTERVAL)

        if not os.path.exists(Connection.LOCK_FILE):
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
