"""The truth table for how a WoowClimate reads its backing entities.

Every case here comes from behaviour observed on real hardware (192.168.2.6, 2026-08-13);
the timestamps in the test names and comments point at the captured logs. The rules being
locked in:

  * the power switch is the only authority on off-vs-running
  * "absent from the state machine" (ZHA rebuilding) and "unavailable" (device unreachable)
    are different things and must stay different
  * only the roles that decide hvac_mode can make this entity unavailable

See docs/adr/0001-backing-state-semantics.md.
"""

from __future__ import annotations

import asyncio

import pytest

from conftest import FakeHass

ROLES = {
    "power": "switch.panel_power",
    "mode": "select.panel_mode",
    "fan": "select.panel_fan",
    "preset": "select.panel_sleep",
    "temperature": "number.panel_setpoint",
    "current_temp": "sensor.panel_current_temp",
}


def build(climate_module, spec=None):
    """A WoowClimate wired to a fake state machine, with every backing entity healthy."""
    spec = spec or climate_module.SM0308C_SPEC
    hass = FakeHass()
    climate = climate_module.WoowClimate(
        hass, spec, "0c:2a:6f:ff:fe:92:22:4e", dict(ROLES), "device-id", "8-58E7101"
    )
    hass.states.set(ROLES["power"], "on")
    hass.states.set(ROLES["mode"], spec.hvac_to_mode_option[climate_module.HVACMode.COOL])
    hass.states.set(ROLES["fan"], "medium")
    hass.states.set(ROLES["preset"], spec.preset_to_option[spec.default_preset])
    hass.states.set(ROLES["temperature"], "26")
    hass.states.set(ROLES["current_temp"], "23.5")
    climate._recompute()
    return climate, hass


# ───────────────────────── the healthy path ─────────────────────────


def test_running_reports_the_selected_mode(climate_module):
    climate, _ = build(climate_module)
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL
    assert climate.available is True
    assert climate._attr_fan_mode == "medium"
    assert climate._attr_target_temperature == 26.0
    assert climate._attr_current_temperature == 23.5


def test_power_off_reports_off_whatever_the_mode_says(climate_module):
    climate, hass = build(climate_module)
    hass.states.set(ROLES["power"], "off")
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF
    assert climate.available is True


# ─────────── the power switch is the only authority on off-vs-running ───────────


@pytest.mark.parametrize("how", ["absent", "unavailable", "unknown"])
def test_unreadable_power_never_infers_a_running_mode(climate_module, how):
    """Regression for the 2026-08-13 18:31:38.886 capture.

    power='unavailable' with a readable mode select made the entity report `cool` for a
    unit that was off. The old code reached the mode branch whenever power was not a
    usable "not on" value; it must now hold instead.
    """
    climate, hass = build(climate_module)
    hass.states.set(ROLES["power"], "off")
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF

    if how == "absent":
        hass.states.remove(ROLES["power"])
    else:
        hass.states.set(ROLES["power"], how)
    climate._recompute()

    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF


def test_mode_unreadable_while_running_holds_the_previous_mode(climate_module):
    climate, hass = build(climate_module)
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL
    hass.states.remove(ROLES["mode"])
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL


def test_power_returning_resumes_normal_tracking(climate_module):
    """Holding is not latching -- once power is readable again it decides immediately."""
    climate, hass = build(climate_module)
    hass.states.set(ROLES["power"], "unavailable")
    climate._recompute()
    hass.states.set(ROLES["power"], "off")
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF


# ───────────── absent and unavailable are different things ─────────────


def test_device_unreachable_makes_the_climate_unavailable(climate_module):
    """Regression for the 2026-08-13 10:13:33.779 capture: every backing entity was
    unavailable and the climate still served fan_only plus a full set of stale attributes.
    """
    climate, hass = build(climate_module)
    for entity_id in ROLES.values():
        hass.states.set(entity_id, "unavailable")
    climate._recompute()
    assert climate.available is False


def test_backing_entities_merely_absent_stay_available(climate_module):
    """ZHA rebuilding its entities lasts milliseconds. Flapping the climate through
    unavailable on every rebuild would be noise, not information.
    """
    climate, hass = build(climate_module)
    for entity_id in ROLES.values():
        hass.states.remove(entity_id)
    climate._recompute()
    assert climate.available is True
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL


@pytest.mark.parametrize("role", ["fan", "preset", "temperature", "current_temp"])
def test_non_essential_role_unavailable_does_not_affect_availability(climate_module, role):
    climate, hass = build(climate_module)
    hass.states.set(ROLES[role], "unavailable")
    climate._recompute()
    assert climate.available is True
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL


@pytest.mark.parametrize("role", ["power", "mode"])
def test_essential_role_unavailable_makes_the_climate_unavailable(climate_module, role):
    climate, hass = build(climate_module)
    hass.states.set(ROLES[role], "unavailable")
    climate._recompute()
    assert climate.available is False


def test_attributes_hold_their_last_value_when_the_backing_goes_away(climate_module):
    climate, hass = build(climate_module)
    hass.states.remove(ROLES["temperature"])
    hass.states.remove(ROLES["current_temp"])
    hass.states.remove(ROLES["fan"])
    climate._recompute()
    assert climate._attr_target_temperature == 26.0
    assert climate._attr_current_temperature == 23.5
    assert climate._attr_fan_mode == "medium"


# ───────────────────────── the accessors themselves ─────────────────────────


def test_raw_keeps_absence_and_unavailable_apart(climate_module):
    climate, hass = build(climate_module)
    assert climate._raw("power") == "on"

    hass.states.set(ROLES["power"], "unavailable")
    assert climate._raw("power") == "unavailable"
    assert climate._state("power") is None

    hass.states.remove(ROLES["power"])
    assert climate._raw("power") is None
    assert climate._state("power") is None


# ───────────────────────── the reconcile safety net ─────────────────────────


def test_the_entity_polls_so_a_missed_event_cannot_be_permanent(climate_module):
    """Regression for the 2026-08-13 10:13:40 capture: a whole ZHA restore batch never
    reached the state-change listener and the entity stayed stale for three minutes,
    recovering only by luck. Staleness is now bounded by SCAN_INTERVAL.
    """
    assert climate_module.WoowClimate._attr_should_poll is True
    assert climate_module.SCAN_INTERVAL.total_seconds() == 60

    climate, hass = build(climate_module)
    # A change that the subscription never delivers ...
    hass.states.set(ROLES["power"], "off")
    assert climate._attr_hvac_mode == climate_module.HVACMode.COOL
    # ... is picked up by the next poll.
    asyncio.run(climate.async_update())
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF


def test_the_platform_watchdog_is_not_hung_off_an_entity(climate_module):
    """An entity that has vanished cannot poll itself back into existence, so the
    rebuild path has to be driven at platform level.
    """
    assert climate_module.WATCHDOG_INTERVAL.total_seconds() == 300


# ───────────────────────── the other supported device ─────────────────────────


def test_the_sibling_panel_follows_the_same_rules(climate_module):
    """The 18:31:38.886 capture was on the SM0308F, which shares this code path."""
    climate, hass = build(climate_module, climate_module.SM0308F_SPEC)
    hass.states.set(ROLES["power"], "off")
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF

    hass.states.set(ROLES["power"], "unavailable")
    hass.states.set(ROLES["mode"], "cool")
    climate._recompute()
    assert climate._attr_hvac_mode == climate_module.HVACMode.OFF
    assert climate.available is False
