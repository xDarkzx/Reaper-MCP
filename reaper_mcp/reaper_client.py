import asyncio
import json
import os
import time

from reaper_mcp_shared.constants import Connection, Timeouts
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode

# Heartbeat: lock file must be updated within this many seconds
_HEARTBEAT_STALE_SECONDS = 60


class ReaperClient:
    def __init__(self):
        self._lock = asyncio.Lock()
        os.makedirs(Connection.IPC_DIR, exist_ok=True)

    def _check_server(self):
        if not os.path.exists(Connection.LOCK_FILE):
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

        # Poll for response
        deadline = time.monotonic() + timeout
        parse_failures = 0
        max_parse_failures = 3
        poll_count = 0
        while time.monotonic() < deadline:
            if os.path.exists(Connection.RESPONSE_FILE):
                try:
                    with open(Connection.RESPONSE_FILE, "r", encoding="utf-8") as f:
                        raw = f.read()
                    if raw.strip():
                        try:
                            result = json.loads(raw)
                            os.remove(Connection.RESPONSE_FILE)
                            return result
                        except json.JSONDecodeError as dec_err:
                            parse_failures += 1
                            if parse_failures >= max_parse_failures:
                                # Best-effort cleanup; ignore if rm fails
                                try:
                                    os.remove(Connection.RESPONSE_FILE)
                                except OSError:
                                    pass
                                raise ReaperMCPError(
                                    ErrorCode.COMMAND_FAILED,
                                    f"Malformed JSON response from REAPER after "
                                    f"{parse_failures} attempts (check REAPER console "
                                    f"for Lua errors): {dec_err}",
                                )
                            time.sleep(Timeouts.POLL_INTERVAL)
                            continue
                except OSError:
                    pass
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
