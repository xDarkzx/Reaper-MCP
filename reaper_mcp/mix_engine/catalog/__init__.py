"""Style profile catalog — auto-loads all genre-family modules and registers profiles.

To add a new style, create a module in this package that calls `register_profile(...)`
at import time, then add it to the import list below.
"""

from reaper_mcp.mix_engine.catalog import edm  # noqa: F401
from reaper_mcp.mix_engine.catalog import rock  # noqa: F401
from reaper_mcp.mix_engine.catalog import pop  # noqa: F401
from reaper_mcp.mix_engine.catalog import electronic  # noqa: F401
from reaper_mcp.mix_engine.catalog import jazz  # noqa: F401
from reaper_mcp.mix_engine.catalog import orchestral  # noqa: F401
from reaper_mcp.mix_engine.catalog import funk_soul  # noqa: F401
