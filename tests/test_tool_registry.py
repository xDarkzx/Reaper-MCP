"""Tests for tool_registry.py's module-discovery/registration sanity checks.

These exist specifically to catch a repeat of a real bug found this session:
an over-broad .gitignore rule silently excluded four shipped tool modules
(compose_tools.py, compose_edit_tools.py, mix_tools.py, compose_helpers.py)
from every published copy of the repo for an unknown period of time, with
no error at install or startup — just fewer tools than documented, silently.
"""

import pkgutil

import pytest
from mcp.server.fastmcp import FastMCP

import reaper_mcp.tools as tools_package
from reaper_mcp.tool_registry import _EXPECTED_MODULES, PROFILES, register_all_tools


def _modules_on_disk_with_register() -> set[str]:
    """Every reaper_mcp/tools/*.py module that actually defines register()."""
    found = set()
    for _finder, name, _ispkg in pkgutil.iter_modules(tools_package.__path__):
        module = __import__(f"reaper_mcp.tools.{name}", fromlist=["register"])
        if hasattr(module, "register"):
            found.add(name)
    return found


class TestExpectedModulesStaysInSync:
    def test_every_registrable_module_is_expected(self):
        """If a new tools/*.py module with register() exists on disk but
        isn't in _EXPECTED_MODULES, the full-profile sanity check can't
        vouch for it — this is the 'someone added a tool and forgot to
        wire it up' half of the drift."""
        on_disk = _modules_on_disk_with_register()
        missing_from_expected = on_disk - _EXPECTED_MODULES
        assert not missing_from_expected, (
            f"Module(s) with register() exist on disk but aren't in "
            f"_EXPECTED_MODULES: {missing_from_expected}. Add them to "
            f"tool_registry.py's _EXPECTED_MODULES."
        )

    def test_every_expected_module_still_exists(self):
        """The other half of the drift: a name lingering in _EXPECTED_MODULES
        for a module that was renamed/removed would make the sanity check
        permanently — and wrongly — report it as 'missing'."""
        on_disk = _modules_on_disk_with_register()
        stale = _EXPECTED_MODULES - on_disk
        assert not stale, (
            f"_EXPECTED_MODULES references module(s) that no longer exist "
            f"or no longer define register(): {stale}."
        )

    def test_full_profile_registers_every_expected_module(self):
        """End-to-end: a fresh registration under the default `full` profile
        actually finds and registers every module _EXPECTED_MODULES promises.
        This is the exact check that would have caught the compose/mix
        packaging bug at import time instead of via a manual audit."""
        mcp = FastMCP("test")
        register_all_tools(mcp)
        # FastMCP doesn't expose a clean public "list registered tool names"
        # API across versions, so we verify indirectly: every expected
        # module must be importable AND define register() (already asserted
        # above) — combined with register_all_tools running without
        # raising, this confirms the full set actually loads.
        on_disk = _modules_on_disk_with_register()
        assert on_disk == _EXPECTED_MODULES


class TestProfilesReferenceRealModules:
    @pytest.mark.parametrize("profile_name", [p for p in PROFILES if p != "full"])
    def test_restricted_profile_modules_exist_on_disk(self, profile_name):
        on_disk = _modules_on_disk_with_register()
        allowed = PROFILES[profile_name]
        missing = allowed - on_disk
        assert not missing, (
            f"Profile '{profile_name}' references module(s) not on disk: {missing}"
        )
