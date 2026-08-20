"""ZHA Quirk (v3) for the Simon i7 0-10V Smart Dimming Remote Switch.

渥屋 catalog: "17-70E857TY"
Manufacturer: _TZ3210_qe3d5gga   (was _TZ3000_qe3d5gga — see "Identity history")
Model:        TS1002
IEEE (test rig): e0:79:8d:ff:fe:b2:d0:42

Identity history — this SKU changed its manufacturer string on OTA
------------------------------------------------------------------
The bench unit was updated on 2026-08-20 and came back as a *different
manufacturer* on the same IEEE:

                        | before             | after
  manufacturer (0x0004) | _TZ3000_qe3d5gga   | _TZ3210_qe3d5gga
  app_version  (0x0001) | 129 (0x81)         | 134 (0x86)
  model        (0x0005) | TS1002             | TS1002 (unchanged)
  EP1/EP2 input         | ... 0xE002         | ... 0xE002 + 0xEF00 (new)

``QuirkBuilder`` matches on manufacturer + model, so the update dropped the
match outright: ZHA reported ``quirk_class = zigpy.device.Device`` and the
device reverted to stock entities (2 switches, Identify, 2 firmware rows) with
no error, no log line and no unavailable entity.  This file now registers the
NEW string only — **a unit still on ``_TZ3000_qe3d5gga`` gets no quirk from
here.**  That is a deliberate trade, recorded in
``docs/adr/0006-ota-can-change-the-manufacturer-match-key.md``.

``app_version`` is written down here rather than matched on: ZHA reads only
manufacturer_name and model_identifier at join, so the value is not populated
when quirks are selected (ADR 0003 measured the same defect on
``firmware_version_filter``).

Both questions the update opened were settled at the panel on 2026-08-20, with
an operator present and zigpy debug capture running:
  * ``0xEF00`` is declared in the signature but **this device never uses it**.
    Across the whole session — taps and slow full-range slides on both gangs —
    ZHA logged not one 0xEF00 frame from `0x824A`, while two other Tuya devices
    on the same coordinator filled the same log with datapoint traffic (a clean
    negative control).  Every state change arrived as a standard ZCL
    ``Report_Attributes`` on 0x0006 / 0x0008.  The quirk does not touch it.
  * **All five operator-verified claims below still hold on app_version 134.**
    Each carries its own 134 evidence inline.

What the device is
------------------
Per the product manual (Simon i7 "Smart Dimming Remote Switch, ZigBee to 0-10V
set"), this is a *wall controller* that pairs with a separate Simon 0-10V
converter module ("N65E0-0017 wireless converter 0-10V with on-off relay" +
"N6524-0412 ZigBee control module") which performs the actual 0-10V dimming.
The wall unit sends on/off + slide-to-dim signals and carries an indicator /
status LED.  The paired unit here has two gangs (endpoints 1 and 2).

Real signature (mains powered, ZigBee Router)
---------------------------------------------
  Endpoint 1 & 2 (identical):
    profile 0x0104, device_type 0x0104 (DIMMER_SWITCH)
    input  (server): 0x0000 Basic, 0x0003 Identify, 0x0004 Groups,
                     0x0006 OnOff, 0x0008 LevelControl, 0xE002 (Tuya mfg),
                     0xEF00 (Tuya MCU — app_version 134 and later only)
    output (client): 0x0003, 0x0006, 0x0008, 0x0019 OTA, 0x0300 Color
  Endpoint 242: Green Power proxy (ZHA skips it)

Stock ZHA behaviour vs. what we want
------------------------------------
Stock ZHA exposes the device as a generic 2-endpoint device: 2 OnOff switches
plus an Identify button and two per-endpoint firmware/OTA "update" entities,
with NO control for the indicator / status LED.

This quirk (modelled on the sibling ``simon_i7_s2100.py``) replaces the stock
OnOff with ``TuyaZBOnOffAttributeCluster`` on each gang.  That:
  * carries the gang ``on_off`` state (exposed as a read-only binary_sensor, see
    the control note below), and
  * surfaces the Tuya indicator-LED attribute ``backlight_mode`` (0x8001),
    which we expose as a single device-global "Status Light" select on EP1.

It also exposes each gang's slide-dim level from the standard LevelControl
cluster as a read-only percent ``sensor`` (see the dimming note below).

It trims the device to the desired set (2 binary_sensors + 2 sensors + 1 select):
  * suppress the control-less default Switch on each gang (replaced by a
    binary_sensor — see the control note),
  * suppress the native StartUpOnOff "power-on behaviour" select on both gangs
    (this device has no Tuya power-on datapoint; the attribute does nothing —
    re-checked on app_version 134: 0x4003 reads None on both endpoints and a
    write leaves it None),
  * suppress the Identify button, and
  * collapse the duplicate per-endpoint firmware/OTA "update" entities.

Status-light values are operator-verified live (see ``WoowStatusLight``).

Dimming note (operator-verified 2026-08-19)
-------------------------------------------
Re-verified on app_version 134, 2026-08-20: both gangs still push.  A tap emits
``Report_Attributes(0x0000, Bool)`` on 0x0006 and a slide emits
``Report_Attributes(0x0000, uint8)`` on 0x0008 — gang 1 walked 170 -> 255 -> 240
-> 137 -> 23 and gang 2 walked 28 -> 63 -> 146 -> 229 -> 255 -> 225 -> 138 -> 23,
each report reaching the sensor within a second.  No polling involved.

``current_level`` (0x0008 / 0x0000) on each gang **does** record the slide-dim
level, contrary to the earlier assumption that it was a static parameter.  Live
over-the-air reads (``allow_cache=False``) while an operator slid gang 2 from
minimum to maximum and back walked the value ``19 -> 196 -> 255 -> 133 -> 0``
over eight seconds, with the gang's ``on_off`` toggling either side of the
gesture as a positive control.  The value **persists** after the gesture — the
earlier flat readings of 0 / 1 / 3 were genuine levels left over from previous
slides, not a dead attribute.  Full scale reads 255, not the ZCL 254, which is
why ``WoowLevelControlCluster`` exists.

ZHA binds and configures reporting for current_level (min 1 s / max 900 s /
change 1) and the device accepts it, so the sensors update on push — no polling.
A device that was paired before this quirk gained the sensors needs one
"Reconfigure device" for that binding to be written.

The rest of the LevelControl attributes (0x0010-0x0014, 0x4000) answer
UNSUPPORTED_ATTRIBUTE, and the manufacturer min/max-brightness attributes the
sibling SM0502 carries (0xFC00 / 0xFC01) do not exist here.

Control note (operator-verified)
--------------------------------
Re-verified on app_version 134, 2026-08-20: all four commands (on/off x EP1/EP2)
came back ``DefaultResponse(status=UNSUP_CLUSTER_COMMAND: 129)`` **from the
device**, and the operator watching the panel saw no lamp move.

This is a *remote* — its server OnOff cluster rejects ``on``/``off`` with
``UNSUP_CLUSTER_COMMAND`` (the real 0-10V load is driven by the separate Simon
converter module, not present in ZHA), so a ``switch`` entity could never
control it.  Each gang only *reports* its ``on_off`` state when physically
tapped, so we model the two gangs as read-only **binary_sensor** entities
(Gang 1 / Gang 2) that mirror the physical state.
"""

import enum
import logging

from zigpy.quirks import CustomCluster
from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zigpy.zcl.clusters.general import Identify, LevelControl, OnOff, Ota

from zhaquirks.tuya import TuyaZBOnOffAttributeCluster

_LOGGER = logging.getLogger(__name__)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id  # 0x0006
IDENTIFY = Identify.cluster_id  # 0x0003
LEVEL = LevelControl.cluster_id  # 0x0008
OTA = Ota.cluster_id  # 0x0019

# current_level full scale, after WoowLevelControlCluster clamps the firmware's
# out-of-spec 255 down to the ZCL maximum.
LEVEL_FULL_SCALE = 254

_ENDPOINTS = (1, 2)  # the two gangs


class WoowLevelControlCluster(CustomCluster, LevelControl):
    """LevelControl that keeps a full-brightness report visible.

    This firmware runs current_level over 0..255, but 0xFF is the ZCL "non value"
    sentinel for uint8, and ZHA drops any sensor value equal to it
    (``zha/application/platforms/sensor/__init__.py`` -> ``_is_non_value``).  A
    slide that reaches the top therefore blanked the Brightness sensor to
    ``unknown`` mid-sweep (operator-verified: 0 -> 70 % -> unknown -> 64 % -> 0).

    Clamping 255 to the ZCL maximum 254 costs nothing — the two are the same
    brightness to a percent-scaled sensor — and keeps full brightness readable as
    100 %.  Reads go through ``_update_attribute`` as well as reports, so both
    paths are covered.

    **Still required on app_version 134** (re-verified 2026-08-20): sliding either
    gang to the top puts the raw frame ``0a 00 00 20 ff`` on the air — uint8 255,
    not the ZCL 254 — on EP1 (15:53:08) and EP2 (15:53:31) alike, and the sensor
    read 100 % rather than blanking.  Remove this clamp and full brightness goes
    back to ``unknown``.
    """

    _CURRENT_LEVEL = LevelControl.AttributeDefs.current_level.id  # 0x0000

    def _update_attribute(self, attrid, value):
        if attrid == self._CURRENT_LEVEL and value == 0xFF:
            value = 0xFE
        super()._update_attribute(attrid, value)


# Status-light (indicator LED) mode — backlight_mode attr 0x8001 on OnOff.
# Raw values + behaviour confirmed live on this device (operator-verified):
#   0 = LED always off
#   1 = LED lit when the gang is ON   (status indicator)
#   2 = LED lit when the gang is OFF  (locator / find-in-dark)
# Re-verified value by value on app_version 134 (2026-08-20, operator at the panel):
#   Close           -> LED stayed dark with the gang both off and on
#   Switch_Status   -> dark when off, lit when on
#   Switch_Position -> lit when off, dark when on  (exact inverse, as labelled)
# The writes also round-trip on 134 through the entity path, and a write on EP1 is
# mirrored on EP2 — which is why one device-global select is correct rather than
# one per gang.
# Labels match the 渥屋/Tuya app and the sibling "3-70E8304" device
# (see WoowIndicatorMode in simon_i7_s2100.py). ZHA renders select options as
# `name.replace("_", " ")`, so member names use underscores for spaces.
class WoowStatusLight(enum.IntEnum):
    Close = 0            # LED never lit (indicator disabled)
    Switch_Status = 1    # LED lit when gang is ON
    Switch_Position = 2  # LED lit when gang is OFF (locator)


def _level_to_pct(value):
    """current_level 0..255 -> 0..100 %. None-safe for the UI."""
    try:
        v = max(0, min(LEVEL_FULL_SCALE, int(value)))
    except (TypeError, ValueError):
        return None
    return round(v / LEVEL_FULL_SCALE * 100)


def _is_button(e) -> bool:
    """True for ZHA button entities (used to drop the Identify button)."""
    return getattr(e, "PLATFORM", "") == "button"


def _is_switch(e) -> bool:
    """True for ZHA switch entities (used to drop the control-less default switch)."""
    return getattr(e, "PLATFORM", "") == "switch"


_builder = QuirkBuilder("_TZ3210_qe3d5gga", "TS1002")

# ── EP1/EP2: OnOff → Tuya OnOff superset (carries on_off + backlight_mode 0x8001).
#    The device rejects on/off (it's a remote), so the default Switch can't control
#    anything — suppress it and expose the gang state as a read-only binary_sensor.
#    Also suppress the dead StartUpOnOff "power-on behaviour" select. ──
for _ep in _ENDPOINTS:
    _builder = (
        _builder.replaces(TuyaZBOnOffAttributeCluster, endpoint_id=_ep)
        .replaces(WoowLevelControlCluster, endpoint_id=_ep)
        .prevent_default_entity_creation(
            endpoint_id=_ep, cluster_id=ONOFF, function=_is_switch
        )
        .prevent_default_entity_creation(
            endpoint_id=_ep, cluster_id=ONOFF, unique_id_suffix="StartUpOnOff"
        )
        .binary_sensor(
            OnOff.AttributeDefs.on_off.name,  # "on_off" (0x0000)
            ONOFF,
            endpoint_id=_ep,
            entity_type=EntityType.STANDARD,
            translation_key=f"gang_{_ep}",
            fallback_name=f"Gang {_ep}",
        )
        # Slide-dim level. Operator-verified live: sliding gang 2 walked
        # current_level 19 -> 196 -> 255 -> 133 -> 0 over 8 s, and the value
        # persists after the gesture (it is the last level, not a transient).
        .sensor(
            WoowLevelControlCluster.AttributeDefs.current_level.name,  # 0x0000
            LEVEL,
            endpoint_id=_ep,
            entity_type=EntityType.STANDARD,
            unit="%",
            suggested_display_precision=0,
            attribute_converter=_level_to_pct,
            translation_key=f"gang_{_ep}_brightness",
            fallback_name=f"Gang {_ep} Brightness",
        )
    )

# ── Drop the Identify button (both EPs each carry an Identify cluster) ──
for _ep in _ENDPOINTS:
    _builder = _builder.prevent_default_entity_creation(
        endpoint_id=_ep, cluster_id=IDENTIFY, function=_is_button
    )

# ── Collapse the duplicate firmware/OTA "update" entities (both EPs) ──
for _ep in _ENDPOINTS:
    _builder = _builder.prevent_default_entity_creation(
        endpoint_id=_ep, cluster_id=OTA, unique_id_suffix="firmware_update"
    )

# ── EP1: single device-global Status-Light (indicator LED) mode select (0x8001) ──
# 0x8001 is mirrored across both gangs; the select is hosted on EP1.
(
    _builder.enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        WoowStatusLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="status_light",
        fallback_name="Status Light",
    ).add_to_registry()
)
