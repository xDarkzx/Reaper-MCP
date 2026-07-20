import ctypes
import os
import sys
import threading
import time

from mcp.server.fastmcp import FastMCP

from reaper_mcp.instructions import load_instructions
from reaper_mcp.reaper_client import ReaperClient
from reaper_mcp.tool_registry import register_all_tools

mcp = FastMCP("ReaperMCP", instructions=load_instructions())
client = ReaperClient()

register_all_tools(mcp)


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
    """Exit this process once the client that spawned it is gone.

    Belt-and-braces alongside stdio EOF detection: if the parent's stdio
    pipes don't propagate EOF cleanly (observed on Windows when the client
    is force-closed rather than shutting down its child processes), this
    catches it independently so the server doesn't outlive its client.

    Requires several consecutive "dead" readings, not just one, before
    actually exiting — a single transient blip in the OS-level check
    shouldn't be enough to kill a server that's still actively serving its
    client.
    """
    ppid = os.getppid()
    consecutive_dead = 0
    while True:
        time.sleep(poll_seconds)
        if _parent_alive(ppid):
            consecutive_dead = 0
            continue
        consecutive_dead += 1
        if consecutive_dead >= confirmations_required:
            os._exit(0)


def main():
    threading.Thread(target=_watch_parent, daemon=True).start()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
