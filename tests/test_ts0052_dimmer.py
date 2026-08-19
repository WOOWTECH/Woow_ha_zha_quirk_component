"""Conversion and validation rules for the TS0052 (241E8016TY) dimmer quirk.

What is worth testing here is the part that has no device in it: the
percent<->raw conversion either round-trips or it silently moves the user's
setting, and the inverted-window guard either fires or the device stores a
window nobody asked for (measured: app_version 132 accepts min 200 / max 100
without complaint and jumps the running level to 200).

Whether the *firmware* honours a written window is not testable here and was
settled on hardware instead -- see `sniffer-related/TS0052-FINDINGS.md`.

These tests need zigpy, which requires Python 3.12+; the rest of the suite runs
on 3.11, so they skip rather than fail when it is absent. To run them:

    <py3.13>/python.exe -m pytest tests/
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("zigpy", reason="zigpy requires Python 3.12+")

from zigpy.exceptions import ZigbeeException  # noqa: E402
from zigpy.zcl import Cluster  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
QUIRK_PY = (
    REPO_ROOT
    / "custom_components"
    / "woow_zha_quirks"
    / "quirks"
    / "ts0052_dimmer_TZ3002_cqpubrcz.py"
)


def _load_quirk():
    """Load the quirk straight from its path.

    Importing it as part of the package would run
    custom_components/woow_zha_quirks/__init__.py, which pulls in the whole
    Home Assistant integration. Same trick conftest.py uses for climate.py.
    """
    spec = importlib.util.spec_from_file_location("_ts0052_quirk", QUIRK_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quirk = _load_quirk()


@pytest.fixture
def level_cluster():
    """A LevelControl cluster with a mock endpoint and an empty attribute cache."""
    return quirk.SimonDimmerLevelControl(MagicMock())


# ---------------------------------------------------------------- conversion


@pytest.mark.parametrize("pct", range(1, 101))
def test_percent_round_trips_without_drift(pct):
    """Every whole percent the entity can hold survives percent->raw->percent.

    A lossy round trip shows up as an entity that snaps to a different number
    the moment it is read back -- the user sets 30 % and sees 29 %.
    """
    assert quirk._pct_from_raw(quirk._raw_from_pct(pct)) == pct


def test_known_raw_values_match_the_hardware():
    """Factory values read off both bench units."""
    assert quirk._pct_from_raw(77) == 30  # factory min
    assert quirk._pct_from_raw(254) == 100  # factory max


def test_raw_conversion_is_clamped_to_a_usable_level():
    """Raw 0 is never emitted, and the top of the scale is 254, not 255.

    255 means "unchanged" to LevelControl, and max = 0 pins the gang at the
    bottom of its range -- the device validates neither (measured: it stores
    anything in 0..255).
    """
    assert quirk._raw_from_pct(0) == 1
    assert quirk._raw_from_pct(-5) == 1
    assert quirk._raw_from_pct(100) == 254
    assert quirk._raw_from_pct(500) == 254


def test_rounding_is_half_up_not_bankers():
    """int(v*254/100 + 0.5), not round().

    On this 254 domain the two disagree at exactly one whole percent, 75 %:
    half-up gives 191, half-to-even gives 190. Both round-trip, so this only
    pins the choice made for consistency with the TS110D sibling quirk -- it is
    not a correctness claim.
    """
    assert quirk._raw_from_pct(75) == 191
    assert round(75 * 254 / 100) == 190
    assert quirk._raw_from_pct(50) == 127


# ---------------------------------------------------------------- get()


def test_get_presents_raw_level_as_percent(level_cluster):
    level_cluster._attr_cache[quirk.MIN_LEVEL] = 77
    assert level_cluster.get(quirk.MIN_LEVEL) == 30


def test_get_leaves_other_attributes_alone(level_cluster):
    """current_level is a real 0..254 level and must not be rescaled."""
    level_cluster._attr_cache[0x0000] = 200
    assert level_cluster.get(0x0000) == 200


def test_get_returns_default_when_uncached(level_cluster):
    assert level_cluster.get(quirk.MIN_LEVEL, "nope") == "nope"


# ---------------------------------------------------------------- writes


@pytest.fixture
def recorded_write(monkeypatch):
    """Capture what the quirk hands to the underlying ZCL write."""
    sent = AsyncMock(return_value=[[]])
    monkeypatch.setattr(Cluster, "write_attributes", sent)
    return sent


def test_write_converts_percent_to_raw(level_cluster, recorded_write):
    """30 % goes out as 76, not the factory 77.

    Both read back as 30 % (77*100/254 = 30.3, 76*100/254 = 29.9), so the entity
    does not visibly drift -- but writing "the same" 30 % the device shipped with
    does move the stored raw level by one step. Harmless at 0.4 % of range, and
    documented here so it is not mistaken for a bug later.
    """
    level_cluster._attr_cache[quirk.MAX_LEVEL] = 254
    asyncio.run(level_cluster.write_attributes({"min_level": 30}))
    assert recorded_write.await_args.args[0] == {"min_level": 76}
    assert quirk._pct_from_raw(76) == quirk._pct_from_raw(77) == 30


def test_write_leaves_non_limit_attributes_untouched(
    level_cluster, recorded_write
):
    asyncio.run(level_cluster.write_attributes({"on_level": 200}))
    assert recorded_write.await_args.args[0] == {"on_level": 200}


def test_write_accepts_a_valid_window(level_cluster, recorded_write):
    level_cluster._attr_cache[quirk.MAX_LEVEL] = 254
    asyncio.run(level_cluster.write_attributes({"min_level": 10}))
    assert recorded_write.await_args is not None


# ---------------------------------------------------------------- guard


def test_min_above_cached_max_is_rejected(level_cluster, recorded_write):
    """The device would accept this and jump the running level to min."""
    level_cluster._attr_cache[quirk.MAX_LEVEL] = 127  # 50 %
    with pytest.raises(ZigbeeException, match="Raise Max Brightness first"):
        asyncio.run(level_cluster.write_attributes({"min_level": 90}))
    recorded_write.assert_not_awaited()


def test_max_below_cached_min_is_rejected(level_cluster, recorded_write):
    level_cluster._attr_cache[quirk.MIN_LEVEL] = 127  # 50 %
    with pytest.raises(ZigbeeException, match="Lower Min Brightness first"):
        asyncio.run(level_cluster.write_attributes({"max_level": 20}))
    recorded_write.assert_not_awaited()


def test_inverted_pair_written_together_is_rejected(
    level_cluster, recorded_write
):
    with pytest.raises(ZigbeeException, match="must be below"):
        asyncio.run(level_cluster.write_attributes({"min_level": 90, "max_level": 20}))
    recorded_write.assert_not_awaited()


def test_equal_min_and_max_is_rejected(level_cluster, recorded_write):
    """max == min leaves a window with nothing in it."""
    level_cluster._attr_cache[quirk.MAX_LEVEL] = 127
    with pytest.raises(ZigbeeException):
        asyncio.run(level_cluster.write_attributes({"min_level": 50}))
    recorded_write.assert_not_awaited()


def test_unknown_partner_is_let_through(level_cluster, recorded_write):
    """Nothing cached to validate against: do not lock the control."""
    asyncio.run(level_cluster.write_attributes({"min_level": 90}))
    assert recorded_write.await_args.args[0] == {"min_level": 229}


# ---------------------------------------------------------------- backlight


def test_backlight_mode_is_uint8_not_enum8():
    """app_version 132 rejects enum8 (0x30) with INVALID_DATA_TYPE.

    The Tuya gateway writes uint8 (0x20) and gets SUCCESS -- sniffed directly.
    zcl_type is what actually goes on the wire.
    """
    attr = quirk.SimonDimmerOnOff.AttributeDefs.backlight_mode
    assert attr.id == 0x8001
    assert attr.zcl_type == 0x20


def test_backlight_retype_does_not_leak_into_upstream():
    """The subclass must not mutate the shared Tuya cluster other quirks use."""
    from zhaquirks.tuya import TuyaZBOnOffAttributeCluster

    assert TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.zcl_type == 0x30


def test_backlight_enum_values_match_the_attribute():
    assert quirk.SimonDimmerBacklightMode.Switch_Status == 0
    assert quirk.SimonDimmerBacklightMode.Close == 1
    assert quirk.SimonDimmerBacklightMode.Switch_Position == 2
