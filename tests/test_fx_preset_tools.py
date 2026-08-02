"""Tests for fx_set_preset's name matching and validation.

Pure logic — no REAPER/IPC mocking needed, matching the pattern of
test_send_tools.py and test_item_tools.py.

The verification itself lives in the Lua handler (fx.fx_set_preset), which
compares the requested name against what is actually loaded afterwards. The
comparison rule is mirrored here so its behaviour is pinned down and
documented: it is the part that decides whether a caller gets a result or an
error, and getting it wrong in either direction is costly — too strict and
legitimate calls fail, too loose and silent no-ops come back as success.
"""

import pytest

from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


class TestPresetNameComparison:
    """Mirror of the trim-based comparison in Lua's fx.fx_set_preset.

    Background: plugins may report preset names padded to a fixed width —
    KORG TRINITY pads every name to 16 characters — while REAPER's own
    presets/*.ini stores the same names trimmed. A caller who took the name
    from that file passes an unpadded string, TrackFX_SetPreset does not
    apply it, and without this check the tool would report success for a
    preset that never changed.
    """

    def _matches(self, requested: str, active: str) -> bool:
        """Mirror of `trim_ws(active) ~= trim_ws(requested)` in the Lua handler."""
        return str(active).strip() == str(requested).strip()

    def test_identical_names_match(self):
        assert self._matches("Trinity Overture", "Trinity Overture")

    def test_unpadded_request_matches_padded_active(self):
        """The .ini spelling vs. what the plugin reports back."""
        assert self._matches("Shakoto", "Shakoto         ")

    def test_padded_request_matches_unpadded_active(self):
        """Symmetric: a plugin may report trimmed while the caller padded."""
        assert self._matches("Shakoto         ", "Shakoto")

    def test_both_padded_match(self):
        assert self._matches("Shakoto         ", "Shakoto         ")

    def test_different_names_do_not_match(self):
        """The no-op case: preset stayed on whatever was loaded before."""
        assert not self._matches("Shakoto", "JamYourButtOff !")

    def test_padding_does_not_make_different_names_equal(self):
        assert not self._matches("Shakoto  ", "Shakotos")

    def test_inner_whitespace_is_significant(self):
        """Only surrounding whitespace is ignored, never inner."""
        assert not self._matches("Big Perc Organ", "BigPercOrgan")

    def test_empty_active_never_matches_a_real_name(self):
        """TrackFX_GetPreset returns "" when it cannot report a preset."""
        assert not self._matches("Shakoto", "")

    def test_case_is_significant(self):
        """No case folding — REAPER matches names case-sensitively."""
        assert not self._matches("shakoto", "Shakoto")


class TestFxSetPresetValidation:
    """Mirror of the argument validation in fx_set_preset."""

    def _validate(self, track_index: int, fx_index: int, preset_name: str):
        if track_index < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0"
            )
        if fx_index < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE, "fx_index must be >= 0"
            )
        if not preset_name:
            raise ReaperMCPError(
                ErrorCode.MISSING_PARAMETER, "preset_name cannot be empty"
            )

    def test_valid_arguments_pass(self):
        self._validate(0, 0, "Trinity Overture")

    def test_negative_track_index_rejected(self):
        with pytest.raises(ReaperMCPError):
            self._validate(-1, 0, "Trinity Overture")

    def test_negative_fx_index_rejected(self):
        with pytest.raises(ReaperMCPError):
            self._validate(0, -1, "Trinity Overture")

    def test_empty_preset_name_rejected(self):
        with pytest.raises(ReaperMCPError):
            self._validate(0, 0, "")

    def test_whitespace_only_name_is_not_empty(self):
        """A padded-to-blank name is still a string the plugin might use;
        rejecting it here would be a guess, so it is passed through and the
        Lua-side verification decides."""
        self._validate(0, 0, "   ")
