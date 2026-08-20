---
status: accepted
date: 2026-08-19
---

# On-device scheduling is left to Home Assistant automations, at the cost of losing it entirely

The SP9-200-14 driver (`_TZ3210_ey6yyb25` / TS0502B) implements two scheduling features in firmware:

| DP | code | carrier | payload |
|---:|------|---------|---------|
| 30 | `rhythm_mode` | Color `0x0300` cmd `0xF6`, attr `0xF009` | 59 bytes: header + six time slots |
| 7  | `countdown`   | OnOff `0x0006` cmd `0xF0`, attr `0xF000` | uint32 seconds |

`rhythm_mode` is a full circadian scheduler: up to six slots of `[hour][minute][brightness %]
[colour temp %]`, a weekday bitmask, and linear interpolation between slots. It is decoded
byte-for-byte and verified — with the schedule running, interpolating between the surrounding slots
predicts the brightness and colour temperature the device reports to within 0.5 %, across two
different schedules. See `docs/simon-product/22-SP9-200-14-tuya-functions.md`.

The quirk exposes neither.

## Context

Home Assistant is a scheduler. Anything `rhythm_mode` can express, an automation can express better:
it can be edited without a 59-byte struct, it can react to sunrise rather than a fixed clock time,
it is visible in the UI, and it is backed up with the rest of the configuration. The same argument
applies with less force to `countdown`, which is a single integer.

Surfacing `rhythm_mode` properly would mean building a six-slot schedule editor out of Home
Assistant entities. There is no good entity shape for that — it would be somewhere between 24 and 36
numbers, or one opaque text field holding hex. Both are worse than an automation.

## What makes this a real decision rather than an obvious one

**It is a one-way door for this device.** Pairing the driver to ZHA removes it from the Tuya
gateway, and with it the Tuya app. A feature the quirk does not expose is not "deferred" in any
practical sense — it becomes unreachable. Getting it back means a factory reset, re-pairing to the
gateway, and reconfiguring everything by hand.

It also cannot be half-done. The schedule lives in one 59-byte write; there is no way to expose
"just the enable flag" without also owning the six slots, because writing the struct requires
supplying all of it.

## Decision

Ship neither `rhythm_mode` nor `countdown` as entities. Use Home Assistant automations for both.

The quirk documents both datapoints, their carriers and their byte layouts, so the decision can be
reversed by writing code rather than by repeating the investigation.

## Consequences

- The device's built-in circadian schedule is inert on ZHA. It is not merely unexposed: after the
  factory reset that re-pairing requires, the schedule is cleared, and nothing can set it again.
- Anyone wanting circadian behaviour writes an automation driving `light.turn_on` with
  `brightness` and `color_temp_kelvin`. That is strictly more capable, and the light itself is
  fully controllable, so nothing is actually lost in capability — only in where the logic lives.
- Battery-free operation is lost in the sense that the schedule now depends on Home Assistant being
  up. For a mains-powered driver in a home that already runs Home Assistant, that is acceptable; for
  an installation where the hub is expected to be absent, it is not, and this decision should be
  revisited.

## Revisit if

The customer is actually using the Tuya app's circadian feature in the field, or asks for lighting
that keeps running a daily curve with the hub switched off. Either turns the trade-off around, and
the byte layouts needed to implement it are already recorded.
