import importlib
import logging
import os
import pkgutil
import sys

from mcp.server.fastmcp import FastMCP

import reaper_mcp.tools as tools_package

logger = logging.getLogger(__name__)


# Approximate per-profile tool counts — for the startup banner. Real count
# is the sum of @mcp.tool() registrations in each module's register().
PROFILES: dict[str, set[str] | None] = {
    # `full` — everything. Default. ~147 tools across 22 modules.
    "full": None,
    # `composition` — write / edit music. Drops FX, mix, sidechain, analysis.
    "composition": {
        "transport_tools", "track_tools", "template_tools", "project_tools",
        "item_tools", "take_tools", "midi_tools", "quantize_tools",
        "marker_tools", "tempo_tools", "selection_tools",
        "compose_tools", "compose_edit_tools", "patterns_tools",
        "loops_tools", "chops_tools",
    },
    # `mixing` — mix + master + bus pipelines + analysis. Drops MIDI/composition.
    "mixing": {
        "transport_tools", "track_tools", "fx_tools", "inventory_tools",
        "mix_tools", "sidechain_tools", "pipeline_tools", "send_tools",
        "envelope_tools", "analysis_tools",
    },
    # `analysis` — inspect + measure. Minimal edit surface.
    "analysis": {
        "transport_tools", "track_tools", "project_tools",
        "analysis_tools", "compose_tools",
    },
    # `minimal` — smoke test / basic REAPER control only.
    "minimal": {
        "transport_tools", "track_tools", "project_tools",
    },
}


def _resolve_profile() -> tuple[str, set[str] | None]:
    """Read REAPER_MCP_PROFILE from env, validate, return (name, module_set)."""
    raw = os.environ.get("REAPER_MCP_PROFILE", "full").strip().lower()
    if raw not in PROFILES:
        sys.stderr.write(
            f"[reaper-mcp] ⚠️  Unknown REAPER_MCP_PROFILE='{raw}'. "
            f"Valid: {', '.join(sorted(PROFILES))}. Falling back to 'full'.\n"
        )
        raw = "full"
    return raw, PROFILES[raw]


def register_all_tools(mcp: FastMCP):
    """Discover and register every tool module in reaper_mcp/tools/.

    A module counts as a tool provider if it defines `register(mcp)`. Modules
    without that function are skipped silently (they may be helpers).

    Respects the REAPER_MCP_PROFILE environment variable. Valid values:
    `full` (default), `composition`, `mixing`, `analysis`, `minimal`.
    A profile filters which modules are registered, trimming the tool surface
    so it fits under LLM tool-count limits (Groq Llama 3 = 128, etc.).

    If a module raises during import or registration, we log loudly and ALSO
    write a banner to stderr so the failure is obvious even when log output
    is hidden by the harness. We keep loading the rest so one broken file
    doesn't take the server down.
    """
    profile_name, allowed = _resolve_profile()

    failures: list[tuple[str, Exception]] = []
    registered: list[str] = []
    skipped_by_profile: list[str] = []

    for finder, name, ispkg in pkgutil.iter_modules(tools_package.__path__):
        if allowed is not None and name not in allowed:
            skipped_by_profile.append(name)
            continue

        try:
            module = importlib.import_module(f"reaper_mcp.tools.{name}")
        except Exception as e:
            logger.error("IMPORT FAILED for tool module %s: %s", name, e, exc_info=True)
            sys.stderr.write(f"\n[reaper-mcp] ❌ Failed to import tool module '{name}': {e}\n")
            failures.append((name, e))
            continue

        if not hasattr(module, "register"):
            logger.debug("Module %s has no register() — skipping", name)
            continue

        try:
            module.register(mcp)
            logger.info("Registered tools from %s", name)
            registered.append(name)
        except Exception as e:
            logger.error("REGISTER FAILED for %s: %s", name, e, exc_info=True)
            sys.stderr.write(f"\n[reaper-mcp] ❌ Tool registration failed for '{name}': {e}\n")
            failures.append((name, e))

    banner = f"[reaper-mcp] Profile '{profile_name}' — registered {len(registered)} tool module(s)"
    if allowed is not None and skipped_by_profile:
        banner += f", skipped {len(skipped_by_profile)} (not in profile)"
    sys.stderr.write(banner + "\n")

    # Profile sanity check — if a profile references a module that doesn't
    # exist on disk, warn so stale profile definitions get caught.
    if allowed is not None:
        missing = sorted(allowed - set(registered) - {n for n, _ in failures})
        # Modules without register() land here too — filter those out.
        truly_missing = []
        for name in missing:
            try:
                importlib.import_module(f"reaper_mcp.tools.{name}")
            except ModuleNotFoundError:
                truly_missing.append(name)
            except Exception:
                pass  # some other problem — already surfaced via failures
        if truly_missing:
            sys.stderr.write(
                f"[reaper-mcp] ⚠️  Profile '{profile_name}' references missing "
                f"module(s): {truly_missing}. Profile definition is out of sync.\n"
            )

    if failures:
        sys.stderr.write(
            f"\n[reaper-mcp] ⚠️  {len(failures)} tool module(s) failed to load: "
            f"{', '.join(n for n, _ in failures)}\n"
            f"[reaper-mcp] The server is running but those tools are unavailable.\n\n"
        )
