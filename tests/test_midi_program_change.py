"""Tests for midi_insert_program_change / midi_list_programs validation.

Pure validation logic — no REAPER/IPC mocking needed, matching the pattern of
test_send_tools.py and test_fx_preset_tools.py.

Both the channel and the program number are 0-based on the wire while REAPER's
UI counts from 1, so the boundaries are where a caller is most likely to be off
by one. These pin them down.
"""

import pytest

from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


class TestProgramChangeValidation:
    """Mirror of the validation in midi_insert_program_change."""

    def _validate(self, track_index=0, channel=0, program=0,
                  bank_msb=None, bank_lsb=None):
        if track_index < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0"
            )
        if channel < 0 or channel > 15:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "Channel must be 0-15")
        if program < 0 or program > 127:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                "program must be 0-127 (0-based; the UI usually shows 1-128)",
            )
        for label, val in (("bank_msb", bank_msb), ("bank_lsb", bank_lsb)):
            if val is not None and not (0 <= val <= 127):
                raise ReaperMCPError(
                    ErrorCode.VALUE_OUT_OF_RANGE, f"{label} must be 0-127, got {val}"
                )

    def test_defaults_are_valid(self):
        self._validate()

    @pytest.mark.parametrize("channel", [0, 15])
    def test_channel_boundaries(self, channel):
        """0-based: channel 15 is what the UI calls 16."""
        self._validate(channel=channel)

    @pytest.mark.parametrize("channel", [-1, 16])
    def test_channel_out_of_range(self, channel):
        """16 is the classic off-by-one — the UI's highest channel."""
        with pytest.raises(ReaperMCPError):
            self._validate(channel=channel)

    @pytest.mark.parametrize("program", [0, 127])
    def test_program_boundaries(self, program):
        self._validate(program=program)

    @pytest.mark.parametrize("program", [-1, 128])
    def test_program_out_of_range(self, program):
        """128 is what the UI shows as the last program — one too many here."""
        with pytest.raises(ReaperMCPError):
            self._validate(program=program)

    def test_bank_bytes_optional(self):
        """Instruments with a single bank need no Bank Select at all."""
        self._validate(bank_msb=None, bank_lsb=None)

    def test_bank_msb_alone_is_allowed(self):
        """Unlike the paired MIDI send channels, these are independent —
        many devices only use the MSB."""
        self._validate(bank_msb=2)

    def test_bank_lsb_alone_is_allowed(self):
        self._validate(bank_lsb=3)

    @pytest.mark.parametrize("value", [0, 127])
    def test_bank_boundaries(self, value):
        self._validate(bank_msb=value, bank_lsb=value)

    @pytest.mark.parametrize("value", [-1, 128])
    def test_bank_msb_out_of_range(self, value):
        with pytest.raises(ReaperMCPError):
            self._validate(bank_msb=value)

    @pytest.mark.parametrize("value", [-1, 128])
    def test_bank_lsb_out_of_range(self, value):
        with pytest.raises(ReaperMCPError):
            self._validate(bank_lsb=value)

    def test_zero_bank_is_not_treated_as_absent(self):
        """Bank 0 is a real value; `if bank_msb:` would silently drop it.
        The implementation checks `is not None` for exactly this reason."""
        self._validate(bank_msb=0, bank_lsb=0)


class TestListProgramsValidation:
    """Mirror of the validation in midi_list_programs."""

    def _validate(self, track_index: int):
        if track_index < 0:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE, "track_index must be >= 0"
            )

    def test_valid_index(self):
        self._validate(0)

    def test_negative_index_rejected(self):
        with pytest.raises(ReaperMCPError):
            self._validate(-1)
