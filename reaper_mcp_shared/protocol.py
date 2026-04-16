import json
import re

from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


_DANGEROUS_CHARS = re.compile(r"[\x00]")


def _validate_string(value: str) -> str:
    if _DANGEROUS_CHARS.search(value):
        raise ReaperMCPError(
            ErrorCode.INJECTION_DETECTED,
            f"Value contains illegal characters: {value!r}",
        )
    return value


def format_command(command: str, **params) -> str:
    """Format a command as JSON for sending to the REAPER TCP server."""
    _validate_string(command)
    for key, val in params.items():
        _validate_string(key)
        if isinstance(val, str):
            _validate_string(val)

    msg = {"command": command, "params": params}
    return json.dumps(msg) + "\n"


def parse_response(raw: str) -> dict:
    """Parse a JSON response from the REAPER TCP server."""
    raw = raw.strip()
    if not raw:
        return {"success": False, "error": "Empty response from REAPER"}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON from REAPER: {e}", "raw": raw}

    return data
