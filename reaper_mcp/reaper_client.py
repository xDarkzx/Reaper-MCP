import asyncio
import json
import os
import sys
import time

from reaper_mcp_shared.constants import Connection, Timeouts
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

# Heartbeat: lock file must be updated within this many seconds
_HEARTBEAT_STALE_SECONDS = 60


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
        self._check_server()
        self._cleanup_files()

        # Write command atomically
        msg = json.dumps({"command": command, "params": params})
        with open(Connection.COMMAND_TMP, "w", encoding="utf-8") as f:
            f.write(msg)
        os.replace(Connection.COMMAND_TMP, Connection.COMMAND_FILE)

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
                            return result
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
