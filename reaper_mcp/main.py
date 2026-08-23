import ctypes
import json
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
from reaper_mcp.tool_registry import describe_profile, register_all_tools, resolve_profile
from reaper_mcp_shared.constants import Connection, ensure_private_dir

_active_profile = resolve_profile()
mcp = FastMCP("ReaperMCP", instructions=load_instructions(_active_profile.instruction_packs))
client = ReaperClient()

register_all_tools(mcp, _active_profile)


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
        with open(tmp, "w", encoding="utf-8") as f:
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
        with open(_generation_file(ppid), encoding="utf-8") as f:
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
            return True
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        return os.getppid() == ppid


def _watch_parent(poll_seconds: float = 3.0, confirmations_required: int = 3) -> None:
    """Exit this process once it's no longer needed — self-directed only,
    never touches another process.
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
    args = sys.argv[1:]
    if "--profile-info" in args or "profile-info" in args:
        profile_target = None
        for i, a in enumerate(args):
            if a in ("--profile", "-p") and i + 1 < len(args):
                profile_target = args[i + 1]
            elif a.startswith("--profile="):
                profile_target = a.split("=", 1)[1]
            elif a not in ("--profile-info", "profile-info", "--json") and not a.startswith("-"):
                profile_target = a

        info = describe_profile(profile_target)
        if "--json" in args:
            print(json.dumps(info.to_dict(), indent=2))
        else:
            print(f"Profile: {info.name}")
            print(f"Tools registered: {info.tool_count}")
            print(f"Tool schema chars: {info.tool_schema_chars}")
            print(f"Instruction chars: {info.instruction_chars}")
            print(f"Instruction packs: {', '.join(info.instruction_packs)}")
            print(f"Modules ({len(info.modules)}): {', '.join(info.modules)}")
            print(f"Tools ({len(info.tools)}): {', '.join(info.tools)}")
        sys.exit(0)

    _claim_generation(os.getppid())
    threading.Thread(target=_watch_parent, daemon=True).start()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
