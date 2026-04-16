import importlib
import logging
import pkgutil
import sys

from mcp.server.fastmcp import FastMCP

import reaper_mcp.tools as tools_package

logger = logging.getLogger(__name__)


def register_all_tools(mcp: FastMCP):
    """Discover and register every tool module in reaper_mcp/tools/.

    A module counts as a tool provider if it defines `register(mcp)`. Modules
    without that function are skipped silently (they may be helpers).

    If a module raises during import or registration, we log loudly and ALSO
    write a banner to stderr so the failure is obvious even when log output
    is hidden by the harness. We keep loading the rest so one broken file
    doesn't take the server down.
    """
    failures: list[tuple[str, Exception]] = []
    for finder, name, ispkg in pkgutil.iter_modules(tools_package.__path__):
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
        except Exception as e:
            logger.error("REGISTER FAILED for %s: %s", name, e, exc_info=True)
            sys.stderr.write(f"\n[reaper-mcp] ❌ Tool registration failed for '{name}': {e}\n")
            failures.append((name, e))

    if failures:
        sys.stderr.write(
            f"\n[reaper-mcp] ⚠️  {len(failures)} tool module(s) failed to load: "
            f"{', '.join(n for n, _ in failures)}\n"
            f"[reaper-mcp] The server is running but those tools are unavailable.\n\n"
        )
