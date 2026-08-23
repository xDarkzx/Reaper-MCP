import importlib
import json
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

import reaper_mcp.tools as tools_package
from reaper_mcp.instructions import load_instructions

# Use tomllib in Python 3.11+, fallback to tomli or json-only
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolProfile:
    """Configuration defining allowed modules, exact tools, and instruction packs."""

    name: str = "custom"
    include_modules: set[str] | None = None
    exclude_modules: set[str] | None = None
    include_tools: set[str] | None = None
    exclude_tools: set[str] | None = None
    instruction_packs: list[str] | None = None

    def is_module_allowed(self, module_name: str) -> bool:
        if self.include_modules is not None and module_name not in self.include_modules:
            return False
        if self.exclude_modules is not None and module_name in self.exclude_modules:
            return False
        return True

    def is_tool_allowed(self, tool_name: str) -> bool:
        if self.include_tools is not None and tool_name not in self.include_tools:
            return False
        if self.exclude_tools is not None and tool_name in self.exclude_tools:
            return False
        return True


@dataclass
class ProfileInfo:
    """Metadata describing a profile's size, tool count, and context footprint."""

    name: str
    tool_count: int
    tool_schema_chars: int
    instruction_chars: int
    modules: list[str]
    tools: list[str]
    instruction_packs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.name,
            "tool_count": self.tool_count,
            "tool_schema_chars": self.tool_schema_chars,
            "instruction_chars": self.instruction_chars,
            "modules": self.modules,
            "tools": self.tools,
            "instruction_packs": self.instruction_packs,
        }


# Built-in profile definitions
BUILTIN_PROFILES: dict[str, ToolProfile] = {
    "full": ToolProfile(
        name="full",
        include_modules=None,
        instruction_packs=None,
    ),
    "composition": ToolProfile(
        name="composition",
        include_modules={
            "transport_tools", "track_tools", "template_tools", "project_tools",
            "item_tools", "take_tools", "midi_tools", "quantize_tools",
            "marker_tools", "tempo_tools", "selection_tools",
            "compose_tools", "compose_edit_tools", "patterns_tools",
            "loops_tools", "chops_tools", "script_tools",
        },
        instruction_packs=["core", "composition", "automation", "editing", "bbc_spitfire", "styles"],
    ),
    "mixing": ToolProfile(
        name="mixing",
        include_modules={
            "transport_tools", "track_tools", "fx_tools", "inventory_tools",
            "mix_tools", "sidechain_tools", "pipeline_tools", "send_tools",
            "envelope_tools", "analysis_tools", "compose_edit_tools",
        },
        instruction_packs=["core", "mixing", "automation", "styles"],
    ),
    "analysis": ToolProfile(
        name="analysis",
        include_modules={
            "transport_tools", "track_tools", "project_tools",
            "analysis_tools", "compose_tools",
        },
        instruction_packs=["core", "postproduction"],
    ),
    "minimal": ToolProfile(
        name="minimal",
        include_modules={
            "transport_tools", "track_tools", "project_tools",
        },
        instruction_packs=["core"],
    ),
    "production": ToolProfile(
        name="production",
        include_modules={
            "transport_tools", "track_tools", "project_tools", "item_tools",
            "take_tools", "midi_tools", "quantize_tools", "selection_tools",
            "fx_tools", "inventory_tools", "mix_tools", "sidechain_tools",
            "envelope_tools", "send_tools", "pipeline_tools",
        },
        instruction_packs=["core", "composition", "automation", "mixing", "styles"],
    ),
}

# Legacy dictionary compatibility for existing imports
PROFILES: dict[str, set[str] | None] = {
    k: v.include_modules for k, v in BUILTIN_PROFILES.items()
}

_EXPECTED_MODULES = frozenset({
    "analysis_tools", "chops_tools", "compose_edit_tools", "compose_tools",
    "demo_tools", "envelope_tools", "fx_tools", "inventory_tools",
    "item_tools", "loops_tools", "marker_tools", "midi_tools", "mix_tools",
    "patterns_tools", "pipeline_tools", "project_tools", "quantize_tools",
    "script_tools", "selection_tools", "send_tools", "sidechain_tools", "take_tools",
    "template_tools", "tempo_tools", "track_tools", "transport_tools",
})


class ToolFilterProxy:
    """Proxy wrapping FastMCP to filter tool registrations against a ToolProfile."""

    def __init__(self, mcp: FastMCP, profile: ToolProfile, on_tool_registered: Callable[[str], None] | None = None):
        self._mcp = mcp
        self._profile = profile
        self._on_tool_registered = on_tool_registered

    def tool(self, *args, **kwargs):
        decorator = self._mcp.tool(*args, **kwargs)

        def wrapper(fn):
            name = kwargs.get("name") or getattr(fn, "__name__", None)
            if name and not self._profile.is_tool_allowed(name):
                logger.debug("Tool '%s' excluded by profile '%s'", name, self._profile.name)
                return fn

            res = decorator(fn)
            if name and self._on_tool_registered:
                self._on_tool_registered(name)
            return res

        return wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mcp, name)


def load_profile_from_file(file_path: str | Path) -> ToolProfile:
    """Load a ToolProfile from a local TOML or JSON file."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Profile file not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(content)
    elif path.suffix.lower() in (".toml", ".ini") or tomllib is not None:
        if tomllib is None:
            raise RuntimeError("TOML parser not available. Use Python 3.11+ or install tomli, or use JSON profile.")
        data = tomllib.loads(content)
    else:
        # Try JSON first, then TOML
        try:
            data = json.loads(content)
        except Exception:
            if tomllib is not None:
                data = tomllib.loads(content)
            else:
                raise ValueError(f"Unsupported profile file format: {file_path}")

    def _to_set(val: Any) -> set[str] | None:
        if val is None:
            return None
        if isinstance(val, (list, tuple, set)):
            return {str(x).strip() for x in val if str(x).strip()}
        if isinstance(val, str):
            return {x.strip() for x in val.split(",") if x.strip()}
        return None

    def _to_list(val: Any) -> list[str] | None:
        if val is None:
            return None
        if isinstance(val, (list, tuple, set)):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str):
            return [x.strip() for x in val.split(",") if x.strip()]
        return None

    return ToolProfile(
        name=str(data.get("name", path.stem)),
        include_modules=_to_set(data.get("include_modules")),
        exclude_modules=_to_set(data.get("exclude_modules")),
        include_tools=_to_set(data.get("include_tools")),
        exclude_tools=_to_set(data.get("exclude_tools")),
        instruction_packs=_to_list(data.get("instruction_packs")),
    )


def resolve_profile() -> ToolProfile:
    """Resolve the active ToolProfile from environment variables or profile file."""
    # 1. Profile file explicitly specified
    file_path = os.environ.get("REAPER_MCP_PROFILE_FILE", "").strip()
    if file_path:
        try:
            base_profile = load_profile_from_file(file_path)
        except Exception as e:
            sys.stderr.write(f"[reaper-mcp] ⚠️ Failed to load profile from '{file_path}': {e}. Falling back to 'full'.\n")
            base_profile = BUILTIN_PROFILES["full"]
    else:
        raw_name = os.environ.get("REAPER_MCP_PROFILE", "full").strip().lower()
        if raw_name in BUILTIN_PROFILES:
            base_profile = BUILTIN_PROFILES[raw_name]
        else:
            sys.stderr.write(
                f"[reaper-mcp] ⚠️ Unknown REAPER_MCP_PROFILE='{raw_name}'. "
                f"Valid: {', '.join(sorted(BUILTIN_PROFILES))}. Falling back to 'full'.\n"
            )
            base_profile = BUILTIN_PROFILES["full"]

    # 2. Apply fine-grained env overrides if present
    include_tools_env = os.environ.get("REAPER_MCP_INCLUDE_TOOLS", "").strip()
    exclude_tools_env = os.environ.get("REAPER_MCP_EXCLUDE_TOOLS", "").strip()
    include_mods_env = os.environ.get("REAPER_MCP_INCLUDE_MODULES", "").strip()
    exclude_mods_env = os.environ.get("REAPER_MCP_EXCLUDE_MODULES", "").strip()

    if any((include_tools_env, exclude_tools_env, include_mods_env, exclude_mods_env)):
        inc_tools = {x.strip() for x in include_tools_env.split(",") if x.strip()} if include_tools_env else base_profile.include_tools
        exc_tools = {x.strip() for x in exclude_tools_env.split(",") if x.strip()} if exclude_tools_env else base_profile.exclude_tools
        inc_mods = {x.strip() for x in include_mods_env.split(",") if x.strip()} if include_mods_env else base_profile.include_modules
        exc_mods = {x.strip() for x in exclude_mods_env.split(",") if x.strip()} if exclude_mods_env else base_profile.exclude_modules

        return ToolProfile(
            name=f"{base_profile.name}-custom",
            include_modules=inc_mods,
            exclude_modules=exc_mods,
            include_tools=inc_tools,
            exclude_tools=exc_tools,
            instruction_packs=base_profile.instruction_packs,
        )

    return base_profile


def register_all_tools(mcp: FastMCP, profile: ToolProfile | None = None) -> list[str]:
    """Discover and register tool modules in reaper_mcp/tools/ matching the profile.

    Respects module and exact tool-level allowlists/blocklists in the ToolProfile.
    """
    if profile is None:
        profile = resolve_profile()

    failures: list[tuple[str, Exception]] = []
    registered_modules: list[str] = []
    registered_tools: list[str] = []
    skipped_by_profile: list[str] = []
    degraded: list[tuple[str, str]] = []

    proxy = ToolFilterProxy(
        mcp=mcp,
        profile=profile,
        on_tool_registered=lambda t: registered_tools.append(t),
    )

    for finder, name, ispkg in pkgutil.iter_modules(tools_package.__path__):
        if not profile.is_module_allowed(name):
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
            module.register(proxy)
            logger.info("Registered tools from %s", name)
            registered_modules.append(name)
            if getattr(module, "_AVAILABLE", True) is False:
                degraded.append((name, getattr(module, "_IMPORT_ERROR", "")))
        except Exception as e:
            logger.error("REGISTER FAILED for %s: %s", name, e, exc_info=True)
            sys.stderr.write(f"\n[reaper-mcp] ❌ Tool registration failed for '{name}': {e}\n")
            failures.append((name, e))

    banner = (
        f"[reaper-mcp] Profile '{profile.name}' — registered {len(registered_tools)} tool(s) "
        f"across {len(registered_modules)} module(s)"
    )
    if skipped_by_profile:
        banner += f", skipped {len(skipped_by_profile)} module(s)"
    sys.stderr.write(banner + "\n")

    if degraded:
        sys.stderr.write(
            f"[reaper-mcp] ⚠️ {len(degraded)} module(s) loaded but registered zero "
            f"tools due to a missing optional dependency: "
            f"{[n for n, _ in degraded]}.\n"
        )

    # Sanity check against expected modules
    expected = (profile.include_modules & _EXPECTED_MODULES) if profile.include_modules is not None else _EXPECTED_MODULES
    missing = sorted(expected - set(registered_modules) - {n for n, _ in failures})
    truly_missing = []
    for name in missing:
        try:
            importlib.import_module(f"reaper_mcp.tools.{name}")
        except ModuleNotFoundError:
            truly_missing.append(name)
        except Exception:  # noqa: S110
            pass
    if truly_missing:
        sys.stderr.write(
            f"[reaper-mcp] ⚠️ Profile '{profile.name}' is missing expected "
            f"module(s) that don't exist on disk: {truly_missing}.\n"
        )

    if failures:
        sys.stderr.write(
            f"\n[reaper-mcp] ⚠️ {len(failures)} tool module(s) failed to load: "
            f"{', '.join(n for n, _ in failures)}\n"
            f"[reaper-mcp] The server is running but those tools are unavailable.\n\n"
        )

    return registered_tools


def describe_profile(profile_or_name: str | ToolProfile | None = None) -> ProfileInfo:
    """Compute context introspection and size metrics for a profile."""
    if isinstance(profile_or_name, ToolProfile):
        profile = profile_or_name
    elif isinstance(profile_or_name, str):
        profile = BUILTIN_PROFILES.get(profile_or_name.lower().strip()) or ToolProfile(name=profile_or_name)
    else:
        profile = resolve_profile()

    instructions_text = load_instructions(profile.instruction_packs)

    # Temporary FastMCP server to measure registered tools and schemas
    test_mcp = FastMCP(f"Introspect-{profile.name}")
    register_all_tools(test_mcp, profile)

    total_schema_chars = 0
    tool_names: list[str] = []
    for tool_name, tool_obj in getattr(test_mcp._tool_manager, "_tools", {}).items():
        tool_names.append(tool_name)
        # FastMCP Tool object has description, parameters/args schema
        desc = getattr(tool_obj, "description", "") or ""
        total_schema_chars += len(desc)
        fn = getattr(tool_obj, "fn", None)
        if fn and hasattr(fn, "__annotations__"):
            total_schema_chars += len(str(fn.__annotations__))

    loaded_packs = profile.instruction_packs if profile.instruction_packs is not None else ["all"]

    # Gather registered module names
    registered_modules = []
    for finder, name, ispkg in pkgutil.iter_modules(tools_package.__path__):
        if profile.is_module_allowed(name):
            registered_modules.append(name)

    return ProfileInfo(
        name=profile.name,
        tool_count=len(tool_names),
        tool_schema_chars=total_schema_chars,
        instruction_chars=len(instructions_text),
        modules=sorted(registered_modules),
        tools=sorted(tool_names),
        instruction_packs=loaded_packs,
    )
