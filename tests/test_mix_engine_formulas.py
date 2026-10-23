"""Tests for mix_engine plugin-parameter formulas — pure math, no REAPER needed.

These are regression tests for three bugs found and fixed in an earlier
hardening pass (ReaVerbate dry gain, Pro-R Decay/Space double-mapping,
Pro-L 2 Output Level ceiling) plus this session's _stereo_width_fx fix and
general dB<->linear/EQ/comp serialization sanity checks. If any of these
ever regress, it's an audibly wrong mix — too-loud reverb, collapsed decay
tails, or a limiter that barely engages.
"""

import pytest

from reaper_mcp.mix_engine.plugins import (
    ReaperStockProfile, FabFilterProfile, _db_to_reaverbate_wet,
    _db_to_reaeq_gain, _q_to_reaeq_bw,
)
from reaper_mcp.mix_engine.master import _ff_limiter, _stereo_width_fx, _rea_limiter
from reaper_mcp.mix_engine.profiles_v2 import (
    EQBand, EQProfile, CompProfile, MasteringChain,
)


# ───────────────────────── regression: ReaVerbate dry gain ─────────────────────────

class TestReaVerbateDryGain:
    def test_dry_is_always_zero(self):
        """Dry must be 0.0 — the reverb sits on a return bus fed by a send,
        so any non-zero dry here double-counts the signal (~3dB too loud,
        the original bug)."""
        entry = ReaperStockProfile().reverb_fx_chain_entry({"wet_db": -6.0})
        assert entry["params_by_index"][1] == 0.0

    def test_dry_is_zero_regardless_of_wet_level(self):
        for wet_db in (-30.0, -12.0, -6.0, 0.0):
            entry = ReaperStockProfile().reverb_fx_chain_entry({"wet_db": wet_db})
            assert entry["params_by_index"][1] == 0.0

    def test_wet_at_unity_is_full_scale(self):
        assert _db_to_reaverbate_wet(0.0) == pytest.approx(1.0)

    def test_wet_at_minus_6db_is_roughly_half(self):
        assert _db_to_reaverbate_wet(-6.0) == pytest.approx(0.501, abs=0.01)

    def test_wet_clamped_to_0_1_range(self):
        assert _db_to_reaverbate_wet(20.0) == 1.0
        # 10**(db/20) is asymptotic — it approaches but never mathematically
        # reaches 0 for a finite dB value, so the lower clamp is a no-op in
        # practice. Assert it's negligibly small, not exactly zero.
        assert _db_to_reaverbate_wet(-100.0) < 0.001


# ───────────────────────── regression: Pro-R Decay/Space ─────────────────────────

class TestProRDecayNotDoubleMapped:
    def test_no_decay_param_set(self):
        """Pro-R's Space already encodes decay behaviour. Feeding room_size
        into a separate Decay param (the original bug) collapsed the decay
        tail at small room sizes and duplicated Space otherwise."""
        entry = FabFilterProfile().reverb_fx_chain_entry({"room_size": 0.3, "dampening": 0.4})
        assert "Decay" not in entry["params"]

    def test_space_reflects_room_size(self):
        entry = FabFilterProfile().reverb_fx_chain_entry({"room_size": 0.75, "dampening": 0.4})
        assert entry["params"]["Space"] == 0.75

    def test_brightness_is_inverse_of_dampening(self):
        entry = FabFilterProfile().reverb_fx_chain_entry({"room_size": 0.5, "dampening": 0.3})
        assert entry["params"]["Brightness"] == pytest.approx(0.7)


# ───────────────────────── regression: Pro-L 2 Output Level ─────────────────────────

class TestProL2OutputLevel:
    def test_minus_1_dbtp_target_engages_limiter_near_ceiling(self):
        """The original buggy formula (0.5 + true_peak_db/60) put a -1 dBTP
        target at ~0.483 — centred 30dB below where it should be, so the
        limiter barely engaged. Correct formula puts -1 dBTP at ~0.983."""
        spec = MasteringChain(true_peak_db=-1.0, limiter_character="transparent")
        entry = _ff_limiter(spec)
        assert entry["params"]["Output Level"] == pytest.approx(0.983, abs=0.001)

    def test_zero_dbtp_is_full_scale(self):
        spec = MasteringChain(true_peak_db=0.0, limiter_character="transparent")
        entry = _ff_limiter(spec)
        assert entry["params"]["Output Level"] == pytest.approx(1.0)

    def test_output_level_clamped_to_0_1(self):
        spec = MasteringChain(true_peak_db=-100.0, limiter_character="transparent")
        entry = _ff_limiter(spec)
        assert 0.0 <= entry["params"]["Output Level"] <= 1.0

    @pytest.mark.parametrize("character,expected", [
        ("transparent", 0.0), ("punchy", 0.2), ("aggressive", 0.6), ("warm", 0.4),
    ])
    def test_limiter_character_maps_to_style(self, character, expected):
        spec = MasteringChain(true_peak_db=-1.0, limiter_character=character)
        entry = _ff_limiter(spec)
        assert entry["params"]["Style"] == expected

    def test_unknown_character_falls_back_to_transparent(self):
        spec = MasteringChain(true_peak_db=-1.0, limiter_character="not_a_real_style")
        entry = _ff_limiter(spec)
        assert entry["params"]["Style"] == 0.0


# ───────────────────────── this session's fix: _stereo_width_fx ─────────────────────────

class TestStereoWidthFx:
    def test_neutral_width_maps_to_normal(self):
        """width=1.0 is documented as neutral; JS: Stereo Enhancer's own
        param scale treats 0.5 as 'normal'."""
        entry = _stereo_width_fx(1.0)
        assert entry["params_by_index"][0] == pytest.approx(0.5)

    def test_wider_than_neutral_increases_param(self):
        entry_neutral = _stereo_width_fx(1.0)
        entry_wide = _stereo_width_fx(1.2)
        assert entry_wide["params_by_index"][0] > entry_neutral["params_by_index"][0]

    def test_narrower_than_neutral_decreases_param(self):
        entry_neutral = _stereo_width_fx(1.0)
        entry_narrow = _stereo_width_fx(0.8)
        assert entry_narrow["params_by_index"][0] < entry_neutral["params_by_index"][0]

    def test_clamped_to_0_1(self):
        assert 0.0 <= _stereo_width_fx(-5.0)["params_by_index"][0] <= 1.0
        assert 0.0 <= _stereo_width_fx(5.0)["params_by_index"][0] <= 1.0


# ───────────────────────── EQ/Comp serialization sanity ─────────────────────────

class TestEQProfileSerialization:
    def test_cuts_and_boosts_split_by_sign(self):
        profile = EQProfile(hp_freq=80.0, bands=[
            EQBand(freq=300, gain_db=-2.0, q=1.2),
            EQBand(freq=3000, gain_db=2.0, q=1.0),
        ])
        d = profile.to_legacy_dict()
        assert len(d["cuts"]) == 1 and d["cuts"][0]["freq"] == 300
        assert len(d["boosts"]) == 1 and d["boosts"][0]["freq"] == 3000

    def test_zero_gain_band_counts_as_boost_not_cut(self):
        # gain_db < 0 goes to cuts, everything else (including exactly 0)
        # goes to boosts — verifying the boundary doesn't silently drop bands.
        profile = EQProfile(hp_freq=80.0, bands=[EQBand(freq=1000, gain_db=0.0, q=1.0)])
        d = profile.to_legacy_dict()
        assert len(d["cuts"]) == 0
        assert len(d["boosts"]) == 1

    def test_hp_freq_passes_through(self):
        profile = EQProfile(hp_freq=42.0)
        assert profile.to_legacy_dict()["hp_freq"] == 42.0


class TestCompProfileSerialization:
    def test_all_fields_present(self):
        comp = CompProfile(threshold_db=-14.0, ratio=4.0, attack_ms=3.0,
                            release_ms=100.0, makeup_db=2.0, knee_db=2.0)
        d = comp.to_dict()
        assert d == {
            "threshold_db": -14.0, "ratio": 4.0, "attack_ms": 3.0,
            "release_ms": 100.0, "makeup_db": 2.0, "knee_db": 2.0,
        }


# ───────── regression: ReaComp/ReaLimit/ReaEQ param maps (issue #41) ─────────
#
# These pin the normalized values against REAPER's own formatted display,
# confirmed live via fx_get_params read-back on a real install (name +
# display string, not inferred). If any of these regress, the stock-plugin
# fallback silently produces a broken mix again — no compression (ratio
# stuck at 1:1), a master ~12dB too quiet, or EQ cuts/boosts off by a
# growing margin from what was asked for.

class TestReaCompParamMap:
    def _entry(self, **overrides):
        profile = {
            "threshold_db": -16.0, "ratio": 3.0, "attack_ms": 20.0,
            "release_ms": 150.0, "makeup_db": 2.0, "knee_db": 6.0,
        }
        profile.update(overrides)
        return ReaperStockProfile().compression_fx_chain_entry(profile)

    def test_threshold_is_amplitude_not_linear_db(self):
        # REAPER reads this back as "-16.0 dB" for this value.
        entry = self._entry(threshold_db=-16.0)
        assert entry["params_by_index"][0] == pytest.approx(0.1585, abs=0.001)

    def test_ratio_is_at_index_1_not_4(self):
        # The original bug: ratio was written to index 4 ("Pre-comp" in the
        # real plugin), so the real Ratio param (index 1) never moved from
        # its default 1:1. REAPER reads 0.0202 back as "~4.00 :1".
        entry = self._entry(ratio=3.0)
        assert entry["params_by_index"][1] == pytest.approx(0.0202, abs=0.001)

    def test_index_4_is_pre_comp_off_not_ratio(self):
        entry = self._entry(ratio=10.0)  # a ratio that would be obviously wrong if index 4 moved
        assert entry["params_by_index"][4] == 0.0

    def test_knee_is_at_index_14_not_5(self):
        entry = self._entry(knee_db=6.0)
        assert 5 not in entry["params_by_index"]
        assert entry["params_by_index"][14] == pytest.approx(0.25, abs=0.001)

    def test_detector_sidechain_filters_are_off(self):
        # Index 6/7 are the detector's own sidechain lowpass/highpass, not
        # "RMS size" and "Makeup" as previously assumed. Left filtered
        # (200Hz lowpass, ~11kHz highpass from the old "RMS"/"makeup" math),
        # the detector hears almost nothing and the compressor barely acts.
        entry = self._entry()
        assert entry["params_by_index"][6] == 1.0   # lowpass off (20kHz, wide open)
        assert entry["params_by_index"][7] == 0.0   # highpass off

    def test_makeup_uses_wet_at_index_11(self):
        # Confirmed live: index 11 ("Wet") is a plain amplitude gain,
        # 10**(dB/20) — setting 0.7/1.3 read back as "-3.1 dB"/"+2.3 dB".
        entry = self._entry(makeup_db=2.0)
        assert entry["params_by_index"][11] == pytest.approx(1.2589, abs=0.001)

    def test_index_5_reserved_is_never_written(self):
        entry = self._entry()
        assert 5 not in entry["params_by_index"]


class TestReaLimitParamMap:
    def test_threshold_and_ceiling_use_different_ranges(self):
        """Threshold is -60..+12dB, ceiling is -24..0dB — previously both
        were normalized over the same -60..0dB range, so an intended 0dB
        threshold actually landed at +12dB and an intended -1dB ceiling
        landed at -0.4dB, cutting the whole master by ~12dB."""
        spec = MasteringChain(true_peak_db=-1.0, limiter_character="transparent")
        entry = _rea_limiter(spec)
        # REAPER reads 0.8333 back as "-0.00 dB" for threshold.
        assert entry["params_by_index"][0] == pytest.approx(0.8333, abs=0.001)
        # REAPER reads 0.9583 back as "-1.00 dB" for ceiling.
        assert entry["params_by_index"][1] == pytest.approx(0.9583, abs=0.001)

    def test_zero_dbtp_ceiling_is_full_scale(self):
        spec = MasteringChain(true_peak_db=0.0, limiter_character="transparent")
        entry = _rea_limiter(spec)
        assert entry["params_by_index"][1] == pytest.approx(1.0)


class TestReaEQGainScale:
    def test_gain_is_exponential_not_linear(self):
        """REAPER reads 0.1986 back as '-2.0 dB' and 0.3333 as '+2.5 dB' —
        confirmed live. The previous linear formula (0.25 + db/24) instead
        wrote 0.1667 for an intended -2dB, which actually displays as
        -3.5dB on the real plugin — a cut 1.75x deeper than asked for."""
        assert _db_to_reaeq_gain(-2.0) == pytest.approx(0.1986, abs=0.001)
        assert _db_to_reaeq_gain(2.5) == pytest.approx(0.3333, abs=0.001)

    def test_zero_db_is_center(self):
        assert _db_to_reaeq_gain(0.0) == pytest.approx(0.25)


class TestReaEQBandwidthDirection:
    def test_higher_q_gives_narrower_not_wider_band(self):
        """The previous q/5.0 mapping made the BW param increase with Q,
        and BW increases with bandwidth — so a higher (narrower-intended)
        Q produced a *wider* band, backwards from what Q means."""
        narrow = _q_to_reaeq_bw(3.0)  # high Q = narrow band
        wide = _q_to_reaeq_bw(0.3)    # low Q = wide band
        assert narrow < wide

    def test_matches_measured_octave_values(self):
        # REAPER's own BW param reads back as octaves/4 (confirmed live:
        # value 0.2 -> display "0.80", value 0.5 -> display "2.00").
        assert _q_to_reaeq_bw(0.7) == pytest.approx(1.9178 / 4.0, abs=0.001)


class TestReaEQDroppedBellBand:
    def test_third_bell_band_is_reported_not_silently_dropped(self, caplog):
        import logging
        profile = {
            "hp_freq": 100.0,
            "cuts": [{"freq": 300, "gain_db": -2.0, "q": 1.2, "shape": "bell"}],
            "boosts": [
                {"freq": 1000, "gain_db": 1.0, "q": 1.0, "shape": "bell"},
                {"freq": 4000, "gain_db": 2.0, "q": 1.2, "shape": "bell"},
            ],
        }
        with caplog.at_level(logging.WARNING):
            entry = ReaperStockProfile().eq_fx_chain_entry(profile)
        assert "4000" in caplog.text or "dropping" in caplog.text.lower()
        # Only 2 bell slots (band 2/3, indices 3-5 and 6-8) exist regardless.
        assert 3 in entry["params_by_index"]
        assert 6 in entry["params_by_index"]
