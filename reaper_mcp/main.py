import ctypes
import os
import sys
import threading
import time

# MCP's stdio transport requires UTF-8 JSON-RPC framing, but Python's default
# stdio encoding follows the OS/locale's default codepage unless told
# otherwise — on Windows that's a legacy ANSI codepage (cp1252 observed on
# the machine this was found on), never UTF-8 unless the system has opted
# into "Use Unicode UTF-8 for worldwide language support" (off by default).
# Not exclusively a Windows problem either — a minimal/Docker Linux image or
# an old system still defaulting to the POSIX/C locale is ASCII-only, same
# failure mode. Tool docstrings throughout this codebase use non-ASCII
# characters (em dashes, arrows like "kick→bass" in the sidechain tools) —
# under a non-UTF-8 encoding those raise UnicodeEncodeError the instant
# they're written to stdout, which is completely unhandled this deep in the
# transport and kills the whole process. Since tools/list (sending every
# registered tool's description) is one of the first things every client
# does on connect, this crashed the server on effectively every session
# start on an affected system, surfacing to the client as "Server
# disconnected" with no further detail. Applied unconditionally, not gated
# to a platform check — a no-op on a system that's already UTF-8, and must
# happen before anything touches stdio (earlier than the FastMCP import even
# risks it), so this is the very first thing in the file.
# Guarded per stream: under pytest (and in embedded hosts) sys.stdin/stdout
# can be a substitute object without .reconfigure, and an AttributeError here
# would make the module unimportable rather than just skipping a no-op.
for _stream in (sys.stdout, sys.stdin, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

from mcp.server.fastmcp import FastMCP

from reaper_mcp.instructions import load_instructions
from reaper_mcp.reaper_client import ReaperClient
from reaper_mcp.tool_registry import register_all_tools
from reaper_mcp_shared.constants import Connection, ensure_private_dir

mcp = FastMCP("ReaperMCP", instructions=load_instructions())
client = ReaperClient()

register_all_tools(mcp)


def _generation_file(ppid: int) -> str:
    return os.path.join(Connection.GENERATION_DIR, f"{ppid}.pid")


def _claim_generation(ppid: int) -> None:
    """Register this process as the current server for `ppid`.

    Purely self-descriptive — this never touches another process. Every
    server for the same parent client writes its own PID here on startup;
    whichever wrote last "wins" the slot. Best-effort: if this fails for any
    reason, this server just never sees itself superseded via this path and
    falls back to the parent-liveness watchdog alone, which is safe.
    """
    try:
        ensure_private_dir(Connection.GENERATION_DIR)
        path = _generation_file(ppid)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            f.write(str(os.getpid()))
        os.replace(tmp, path)  # atomic — readers never see a torn write
    except OSError:
        pass


def supersede_enabled(env: dict | None = None) -> bool:
    """Whether the "a newer server took over" self-retirement path is active.

    Set REAPER_MCP_NO_SUPERSEDE=1 to switch it off. Needed for clients that
    open more than one connection under a single parent process: the
    generation slot is keyed by parent PID, so a second concurrent
    connection from the same client looks identical to that client having
    reconnected, and the first server retires while its connection is still
    in active use. Observed with Claude Desktop, which spawns two servers
    under one parent — the client keeps talking to the first one, which
    exits, and every tool call then hangs with no response.

    Switching this off leaves the two mechanisms that actually own shutdown
    intact: stdio EOF when the client closes the pipes, and the
    parent-liveness watchdog. Those cover the normal cases; this path is
    belt-and-braces for clients that reconnect without cleaning up.
    """
    if env is None:
        env = os.environ
    return env.get("REAPER_MCP_NO_SUPERSEDE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def _superseded(ppid: int) -> bool:
    """True once a newer server has claimed this parent's generation slot.

    Written via atomic replace, so a read here is never torn — unlike the
    parent-liveness check, this signal is authoritative the moment it
    differs, no debounce needed. On any read failure, fail safe: assume NOT
    superseded (this server keeps running rather than guessing itself away).
    """
    try:
        with open(_generation_file(ppid)) as f:
            current = int(f.read().strip())
    except (OSError, ValueError):
        return False
    return current != os.getpid()


def _parent_alive(ppid: int) -> bool:
    """Best-effort liveness check. MUST fail open (assume alive) whenever the
    check itself is inconclusive — this feeds a self-termination decision, so
    a false "dead" is far worse than a missed "actually dead" (a missed one
    just gets caught on the next poll; a false one kills a healthy server
    outright, with no recovery).
    """
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, ppid
        )
        if not handle:
            # Can't open a handle — this can happen for reasons unrelated to
            # the parent being dead (e.g. the parent runs in a different,
            # more restrictive security context, such as an MSIX/AppContainer
            # sandbox). Treat "can't tell" as alive, not dead.
            return True
        try:
            # WAIT_OBJECT_0 (0) means the process handle is signaled, i.e. exited
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        return os.getppid() == ppid


def _watch_parent(poll_seconds: float = 3.0, confirmations_required: int = 3) -> None:
    """Exit this process once it's no longer needed — self-directed only,
    never touches another process.

    Two independent reasons to retire:

    1. Superseded: the same parent client started a newer server for itself
       (e.g. it reconnected without stopping this one). Checked every poll;
       acts immediately since the generation file is authoritative.
    2. Orphaned: the parent client process itself is gone. Belt-and-braces
       alongside stdio EOF detection — if the parent's stdio pipes don't
       propagate EOF cleanly (observed on Windows when the client is
       force-closed rather than shutting down its child processes), this
       catches it independently. Requires several consecutive "dead"
       readings, not just one, before acting — a single transient blip in
       the OS-level check shouldn't be enough to exit a server that's still
       actively serving its client.
    """
    ppid = os.getppid()
    consecutive_dead = 0
    check_superseded = supersede_enabled()
    while True:
        time.sleep(poll_seconds)
        if check_superseded and _superseded(ppid):
            os._exit(0)
        if _parent_alive(ppid):
            consecutive_dead = 0
            continue
        consecutive_dead += 1
        if consecutive_dead >= confirmations_required:
            os._exit(0)


def main():
    _claim_generation(os.getppid())
    threading.Thread(target=_watch_parent, daemon=True).start()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
