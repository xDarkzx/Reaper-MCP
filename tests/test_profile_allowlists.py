import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from reaper_mcp.instructions import load_instructions
from reaper_mcp.tool_registry import (
    ToolFilterProxy,
    ToolProfile,
    describe_profile,
    load_profile_from_file,
    register_all_tools,
    resolve_profile,
)


def test_tool_filter_proxy_exact_includes_and_excludes():
    mcp = FastMCP("TestProxy")
    profile = ToolProfile(
        name="custom",
        include_tools={"track_get_all", "fx_get_chain"},
        exclude_tools={"fx_get_chain"},
    )
    registered = []
    proxy = ToolFilterProxy(mcp, profile, on_tool_registered=lambda t: registered.append(t))

    @proxy.tool()
    def track_get_all():
        """Get all tracks."""
        return {"tracks": []}

    @proxy.tool()
    def fx_get_chain():
        """Get FX chain."""
        return {"fx": []}

    @proxy.tool()
    def transport_play():
        """Play."""
        return {"play": True}

    tools_in_mcp = list(mcp._tool_manager._tools.keys())
    assert "track_get_all" in tools_in_mcp
    assert "fx_get_chain" not in tools_in_mcp  # excluded
    assert "transport_play" not in tools_in_mcp  # not in include_tools
    assert registered == ["track_get_all"]


def test_load_instructions_modular_packs():
    # Full loads all
    full_text = load_instructions(None)
    assert "CRITICAL RULES" in full_text
    assert "Composition Workflow" in full_text
    assert "Mixing" in full_text
    assert "BBC Spitfire CC Reference" in full_text

    # Minimal loads only core
    core_only = load_instructions(["core"])
    assert "CRITICAL RULES" in core_only
    assert "Composition Workflow" not in core_only
    assert "BBC Spitfire CC Reference" not in core_only
    assert len(core_only) < len(full_text)

    # Specific combination
    custom = load_instructions(["core", "mixing", "styles"])
    assert "CRITICAL RULES" in custom
    assert "Mixing" in custom
    assert "Style Cheat Sheet" in custom
    assert "Composition Workflow" not in custom


def test_load_profile_from_json_file(tmp_path: Path):
    profile_data = {
        "name": "audio-automation-json",
        "include_modules": ["project_tools", "track_tools", "fx_tools"],
        "include_tools": ["project_get_overview", "track_get_all", "fx_get_chain"],
        "instruction_packs": ["core", "postproduction"],
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data), encoding="utf-8")

    profile = load_profile_from_file(profile_file)
    assert profile.name == "audio-automation-json"
    assert profile.include_modules == {"project_tools", "track_tools", "fx_tools"}
    assert profile.include_tools == {"project_get_overview", "track_get_all", "fx_get_chain"}
    assert profile.instruction_packs == ["core", "postproduction"]


def test_load_profile_from_toml_file(tmp_path: Path):
    toml_content = """
name = "audio-automation-toml"
include_modules = ["project_tools", "track_tools"]
include_tools = ["track_get_all", "track_get_info"]
instruction_packs = ["core"]
"""
    profile_file = tmp_path / "profile.toml"
    profile_file.write_text(toml_content, encoding="utf-8")

    profile = load_profile_from_file(profile_file)
    assert profile.name == "audio-automation-toml"
    assert profile.include_modules == {"project_tools", "track_tools"}
    assert profile.include_tools == {"track_get_all", "track_get_info"}
    assert profile.instruction_packs == ["core"]


def test_resolve_profile_environment_overrides(monkeypatch):
    monkeypatch.setenv("REAPER_MCP_PROFILE", "minimal")
    monkeypatch.setenv("REAPER_MCP_INCLUDE_TOOLS", "track_get_all,transport_play")
    monkeypatch.setenv("REAPER_MCP_EXCLUDE_TOOLS", "transport_play")

    profile = resolve_profile()
    assert profile.name == "minimal-custom"
    assert profile.include_tools == {"track_get_all", "transport_play"}
    assert profile.exclude_tools == {"transport_play"}
    assert profile.is_tool_allowed("track_get_all") is True
    assert profile.is_tool_allowed("transport_play") is False
    assert profile.is_tool_allowed("track_create") is False


def test_describe_profile_metrics():
    minimal_info = describe_profile("minimal")
    assert minimal_info.name == "minimal"
    assert minimal_info.tool_count > 0
    assert minimal_info.tool_count < 60
    assert minimal_info.instruction_chars < 5000
    assert "track_get_all" in minimal_info.tools
    assert "midi_insert_note" not in minimal_info.tools

    mixing_info = describe_profile("mixing")
    assert mixing_info.name == "mixing"
    assert "fx_get_chain" in mixing_info.tools
    assert "midi_insert_note" not in mixing_info.tools

    full_info = describe_profile("full")
    assert full_info.tool_count >= 170
    assert full_info.instruction_chars > minimal_info.instruction_chars


def test_exact_tool_allowlist_registration():
    custom_profile = ToolProfile(
        name="narrow-test",
        include_modules={"track_tools", "fx_tools"},
        include_tools={"track_get_all", "fx_get_chain", "fx_get_params"},
    )
    test_mcp = FastMCP("NarrowMCP")
    registered_tools = register_all_tools(test_mcp, custom_profile)

    assert set(registered_tools) == {"track_get_all", "fx_get_chain", "fx_get_params"}
    tools_in_mcp = set(test_mcp._tool_manager._tools.keys())
    assert tools_in_mcp == {"track_get_all", "fx_get_chain", "fx_get_params"}
    assert "track_create" not in tools_in_mcp
    assert "fx_add" not in tools_in_mcp
