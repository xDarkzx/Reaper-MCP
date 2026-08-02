"""Tests for the REAPER_MCP_NO_SUPERSEDE opt-out in reaper_mcp/main.py.

The supersede path retires a server when a newer one claims the generation
slot for the same parent PID. That assumes one connection per client, which
does not hold for every MCP client — Claude Desktop opens two servers under
a single parent process, and the first one then exits while the client is
still using it, leaving every tool call to hang.

`supersede_enabled` takes the environment as an argument so the parsing can
be tested without touching os.environ or importing the whole server.
"""

import pytest

from reaper_mcp.main import supersede_enabled


class TestSupersedeOptOut:
    def test_enabled_by_default(self):
        """Unset variable keeps the existing behaviour — no silent change."""
        assert supersede_enabled({}) is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
    def test_recognised_off_values(self, value):
        assert supersede_enabled({"REAPER_MCP_NO_SUPERSEDE": value}) is False

    @pytest.mark.parametrize("value", ["TRUE", "Yes", "On", "1"])
    def test_case_insensitive(self, value):
        assert supersede_enabled({"REAPER_MCP_NO_SUPERSEDE": value}) is False

    @pytest.mark.parametrize("value", [" 1", "1 ", "  true  "])
    def test_surrounding_whitespace_tolerated(self, value):
        """Values coming from a JSON config or a shell export often carry
        stray whitespace; that should not silently re-enable the path."""
        assert supersede_enabled({"REAPER_MCP_NO_SUPERSEDE": value}) is False

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_other_values_leave_it_enabled(self, value):
        """Anything that is not an explicit opt-out keeps the default. An
        unrecognised value must not disable a safety mechanism by accident."""
        assert supersede_enabled({"REAPER_MCP_NO_SUPERSEDE": value}) is True

    def test_reads_os_environ_when_no_argument_given(self, monkeypatch):
        monkeypatch.setenv("REAPER_MCP_NO_SUPERSEDE", "1")
        assert supersede_enabled() is False
        monkeypatch.delenv("REAPER_MCP_NO_SUPERSEDE")
        assert supersede_enabled() is True
