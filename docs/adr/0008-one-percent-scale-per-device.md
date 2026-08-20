---
status: accepted
date: 2026-08-20
---

# Brightness and min/max brightness share one percent scale, and the device decides which one it is

A dimmer in this repo usually exposes two kinds of percentage: what the light is doing now
(`current_level` as a percent) and where its limits are (minimum / maximum brightness). Users read
them side by side and expect them to mean the same thing — set the minimum to 50 %, dim all the way
down, see 50 %.

They only line up if both are computed on the same scale, and *which* scale that has to be is not a
matter of taste. It is whichever one the device itself defines.

## The two shapes this takes

**The limit is stored as a raw level.** `ts0052_dimmer_TZ3002_cqpubrcz.py` is this shape: min/max
live in LevelControl `0x0002` / `0x0003` in the same 0..254 domain as `current_level`, so the quirk
converts them into the brightness scale and says so at the constant:

```python
# LevelControl current_level tops out at 254 (255 = "unchanged"); use it as the
# 100 % reference so the min/max brightness percent lines up with brightness.
_FULL = 254
```

Here the *limits* move to meet brightness. `ts110d_dimmer_TZ3210_1znecg8a.py` does the same over the
same domain.

**The limit is stored as a percent, in the device's own units.** `simon_i7_70e857ty_dimmer.py` is
this shape: minimum brightness is Tuya DP 103 / 104, natively a percent, and that percent is
**1-based** — 1 % means raw 0. The device converts `raw = round((pct − 1) × 255/100)`, verified at
four settings. A 0-based brightness percent therefore reads exactly one point lower at the floor:
set 50, slide to the bottom, see 49 %.

Here brightness moves to meet the limits, because the limit *is* the device's own definition of
what a percent means on this hardware. `_level_to_pct()` is the inverse of the device's formula,
`min(100, round(raw / 255 × 100) + 1)`.

## Decision

**One percent scale per device, across brightness and its limits. When they disagree, the side that
holds the device's own definition wins and the other converts to it.**

Applies to new quirks and to changes in existing ones. Not retroactive: `simon_sm0502_dimmer.py`
converts over 255 while TS0052 and TS110D use 254, and those three are each internally consistent
and deployed at customer sites. The inconsistency between them is recorded here rather than fixed,
because changing them would move the numbers under installations that are working.

## What this cost, and what it did not

Adopting the device's 1-based scale on the 70E857TY shifts every brightness reading up one point
(raw 127 reads 51 % rather than 50 %) and has two edges:

- the sensor can no longer read 0 % — raw 0 reads 1 % — which is unreachable in practice while the
  minimum is 5 or above (its floor is raw 10);
- raw 252..255 all read 100 %, where before it was 253..254.

Checked arithmetically over the exposed range: the floor equals the Min Brightness number for all
46 settings from 5 to 50, and the mapping stays monotonic across all 256 raw values.

## A correction worth keeping

An earlier version of this decision went the other way — the offset was left in place, and the
justification was that the Min Brightness number should match what the Tuya app displays for the
same setting. That was overturned within a day, and the reason is the useful part: **the app-parity
premise was never verified.** Nobody had read the app's UI; it was inferred from the values the
device received when the operator drove the slider to its ends. It lost to something that could be
checked — TS0052's existing choice, in this repo, with its reasoning written at the constant.

Prefer the premise you can go and read over the one you would have to go and measure.
