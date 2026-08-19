"""Brightness handling for the 17-70E857TY (Simon i7 0-10V dimming remote) quirk.

What is worth testing here is the part with no device in it: the firmware runs
current_level over 0..255, but 0xFF is the ZCL "non value" sentinel for uint8
and ZHA blanks any sensor whose raw value equals it -- measured live, a slide
that reached the top drove the Brightness sensor 0 -> 70 % -> unknown -> 64 %.
WoowLevelControlCluster clamps that 255 away; if the clamp regresses, the
sensor silently goes blank at full brightness again.

That the attribute tracks the slide at all was settled on hardware instead
(2026-08-19: gang 2 walked 19 -> 196 -> 255 -> 133 -> 0 over eight seconds).

These tests need zigpy, which requires Python 3.12+; the rest of the suite runs
on 3.11, so they skip rather than fail when it is absent. To run them:

    <py3.13>/python.exe -m pytest tests/
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("zigpy", reason="zigpy requires Python 3.12+")

REPO_ROOT = Path(__file__).resolve().parent.parent
QUIRK_PY = (
    REPO_ROOT
    / "custom_components"
    / "woow_zha_quirks"
    / "quirks"
    / "simon_i7_70e857ty_dimmer.py"
)


def _load_quirk():
    """Load the quirk straight from its path (same trick as the TS0052 tests)."""
    spec = importlib.util.spec_from_file_location("_70e857ty_quirk", QUIRK_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quirk = _load_quirk()

CURRENT_LEVEL = quirk.WoowLevelControlCluster.AttributeDefs.current_level.id


@pytest.fixture
def level_cluster():
    """A WoowLevelControlCluster with a mock endpoint."""
    return quirk.WoowLevelControlCluster(MagicMock())


# ---------------------------------------------------------------- conversion


def test_percent_conversion_spans_the_scale():
    assert quirk._level_to_pct(0) == 0
    assert quirk._level_to_pct(quirk.LEVEL_FULL_SCALE) == 100


def test_measured_levels_convert_to_sensible_percents():
    """Values captured off the bench unit during a live slide."""
    assert quirk._level_to_pct(19) == 7
    assert quirk._level_to_pct(133) == 52
    assert quirk._level_to_pct(196) == 77


def test_conversion_is_none_safe_and_clamped():
    """The UI must not raise on a missing or out-of-range value."""
    assert quirk._level_to_pct(None) is None
    assert quirk._level_to_pct("nonsense") is None
    assert quirk._level_to_pct(-5) == 0
    assert quirk._level_to_pct(999) == 100


# ------------------------------------------------------------------- clamping


def test_full_brightness_is_not_reported_as_the_non_value_sentinel(level_cluster):
    """255 must never reach ZHA, or the sensor blanks to `unknown` at full."""
    level_cluster._update_attribute(CURRENT_LEVEL, 255)
    assert level_cluster.get("current_level") == 254
    assert quirk._level_to_pct(level_cluster.get("current_level")) == 100


@pytest.mark.parametrize("raw", [0, 1, 19, 133, 196, 254])
def test_ordinary_levels_pass_through_untouched(level_cluster):
    """Only the sentinel is rewritten; every other level is the device's own."""
    for raw in (0, 1, 19, 133, 196, 254):
        level_cluster._update_attribute(CURRENT_LEVEL, raw)
        assert level_cluster.get("current_level") == raw


def test_other_attributes_are_not_clamped(level_cluster):
    """The clamp is scoped to current_level, not to every uint8 on the cluster."""
    on_level = quirk.WoowLevelControlCluster.AttributeDefs.on_level.id
    level_cluster._update_attribute(on_level, 255)
    assert level_cluster.get("on_level") == 255
