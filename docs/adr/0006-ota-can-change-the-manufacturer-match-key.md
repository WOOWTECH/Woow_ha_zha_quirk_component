---
status: accepted
date: 2026-08-20
---

# A Tuya OTA can change the manufacturer string, so the quirk match key is not a stable identity

ADR 0003 resolved firmware divergence *inside* one quirk registration. Its whole argument rests on
an assumption it never states: that `manufacturer_name` / `model_identifier` — the pair
`QuirkBuilder` matches on — identify a physical unit for its lifetime, and that a firmware revision
can only show up in some *other* field. On 2026-08-20 that assumption failed on hardware.

## What happened

The bench 17-70E857TY was OTA-updated. Same physical unit, same IEEE, and the Basic cluster now
reads:

| | before | after |
|---|---|---|
| IEEE | `e0:79:8d:ff:fe:b2:d0:42` | `e0:79:8d:ff:fe:b2:d0:42` (unchanged) |
| **manufacturer_name (0x0004)** | **`_TZ3000_qe3d5gga`** | **`_TZ3210_qe3d5gga`** |
| model_identifier (0x0005) | `TS1002` | `TS1002` |
| **app_version (0x0001)** | **129 (0x81)** | **134 (0x86)** |
| zcl / hw version | 8 / 1 | 8 / 1 |
| EP1+EP2 input clusters | `0000 0003 0004 0006 0008 E002` | `0000 0003 0004 0006 0008 E002` **`EF00`** |

The OTA moved the device between Tuya manufacturer prefixes (`_TZ3000_` → `_TZ3210_`), kept the
suffix, bumped the firmware, and added a Tuya MCU cluster. `simon_i7_70e857ty_dimmer.py` registered
`QuirkBuilder("_TZ3000_qe3d5gga", "TS1002")`, so after the update ZHA reported
`quirk_class = zigpy.device.Device` and the device fell back to stock entities: two `switch` (which
this remote cannot drive), an Identify `button`, two duplicate firmware `update` rows. The three
quirk entities — two gang binary_sensors, two Brightness sensors, one Status Light select — were
gone.

Nothing announced this. There is no error, no log line, no unavailable entity: the device simply
comes back wearing a different set of entities.

## Decision

**When an OTA changes the manufacturer string, move the registration to the new string. Do not keep
the old one alongside it.**

`simon_i7_70e857ty_dimmer.py` now registers `("_TZ3210_qe3d5gga", "TS1002")` and nothing else. The
old identity survives only as a paragraph in the quirk's docstring.

Keeping both was considered and is the cheaper-looking option — a two-element loop, as
`ts0002_switch_TZ3000_denobasq.py` already does across manufacturers. It was rejected deliberately:
the old string is a *pre-update* identity of a device that is expected to be updated, not a second
SKU. Carrying it forward would leave the file claiming support for a configuration nobody is
supposed to be running, and every later change would have to be reasoned about twice.

## Consequences

- **Any 70E857TY still on the shipping firmware silently loses its quirk.** This is the cost of the
  decision and it is worth naming precisely, because it is exactly what ADR 0003's standard —
  *"build to the newer firmware and let the older one fail loudly"* — cannot deliver here. There,
  the old firmware kept its quirk and failed at the moment of a write, with a real message in the
  UI. Here there is no write to fail: the match itself misses, and the failure surfaces as entities
  that quietly changed shape. **Loud failure was not available as an option.** The mitigation is
  operational, not technical: a field unit showing two plain switches instead of Gang 1 / Gang 2 has
  not broken, it has not been updated.
- **Diagnosis order changes.** When a device "loses" its quirk after an update, compare the
  manufacturer string *before* comparing firmware versions. The symptom of a stale match key and the
  symptom of a firmware behaviour change look identical from the entity list.
- **ADR 0003's "app_version is the only field that separates these units" is model-specific.** On
  this SKU the manufacturer prefix moved with the firmware, which means the two revisions *are*
  separable by the match key — but only by accident, and only in one direction. It does not
  generalise, and it does not rehabilitate registration-time firmware branching: 0003's timing
  objection (the value is unpopulated when quirks are matched) is untouched by this.
- **`0xEF00` is now present and unhandled.** The quirk does not touch it. Whether the gang state and
  the slide-dim level still travel over the standard `0x0006` / `0x0008` clusters on this firmware,
  or have moved to Tuya datapoints, is unverified — it can only be answered with an operator at the
  panel, and the quirk's two Brightness sensors depend on the answer.

## Scope

One SKU, one OTA, observed once. Whether other Tuya models in this repo change prefix on update is
untested. The repo has 34 quirks keyed on a manufacturer string, and this failure mode is invisible
in all of them until the day it happens.
