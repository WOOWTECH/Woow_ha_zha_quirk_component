---
status: accepted
date: 2026-08-18
amended: 2026-08-18
---

# Firmware divergence inside one quirk registration is resolved at runtime, not by registration

> **Amended the same day it was written.** The first draft contained two factual errors, each of
> which pushed the decision the wrong way. Both are corrected inline below and called out in
> *Corrections*. The conclusion changed as a result: a single registration exposing writable
> controls to every unit, which the first draft rejected.

Two 241E8016TY samples (TS0052 / `_TZ3002_cqpubrcz`) on the bench disagree about what the device can
do, and the disagreement is invisible to the mechanism quirks use to select themselves.

| | V1 | V2 |
|---|---|---|
| IEEE | `8c:8b:48:ff:fe:d9:c6:d6` | `7c:c6:b6:ff:fe:82:e3:7f` |
| manufacturer_name (0x0004) | `_TZ3002_cqpubrcz` | `_TZ3002_cqpubrcz` |
| model_identifier (0x0005) | `TS0052` | `TS0052` |
| **app_version (0x0001)** | **129** | **132** |
| zcl / stack / hw version | 3 / 0 / 1 | 3 / 0 / 1 |
| date_code, sw_build_id | `2019.3.20`, empty | `2019.3.20`, empty |

`QuirkBuilder` matches on **manufacturer and model only**. Every other identity field is identical,
so both units necessarily load the same quirk.

## The two divergences

**Backlight `OnOff 0x8001` — the declared ZCL type changed, and the two are mutually exclusive.**
fw 129 accepts `enum8` (`0x30`) and rejects `uint8`; fw 132 does the exact opposite, rejecting
`enum8` with `0x8D INVALID_DATA_TYPE`. Both directions are measured on hardware. **No single
declared type can serve both revisions** — only a runtime retry could.

**Min/Max brightness `LevelControl 0x0002` / `0x0003` — read-only became writable.** fw 129 rejects
every write with `READ_ONLY 0x88` (27/27, including writes from the Tuya gateway itself). fw 132
accepts them and the firmware genuinely enforces the window — on HA `move_to_level` and on the
physical wall button alike.

Full evidence: `sniffer-related/TS0052-FINDINGS.md`, section "V1 vs V2 differential", and issue
[#6](https://github.com/WOOWTECH/Woow_ha_zha_quirk_component/issues/6).

## Decision

**One registration per manufacturer/model. Where the revisions differ, build to the newer firmware
and let the older one fail loudly.**

The quirk exposes Min/Max Brightness as writable `number` entities to every unit and writes
`0x8001` as `uint8`. On fw 129 both operations fail with a real error in the Home Assistant UI:

```
Failed to write attribute min_level=30: <Status.READ_ONLY: 136>
Failed to write attribute backlight_mode=<...Close: 1>: <Status.INVALID_DATA_TYPE: 141>
```

This is a deliberate trade, not an oversight: **fw 129 loses a working backlight control that it
had before this change.** It was accepted because fw 129 is a bench sample, not a shipping
revision. If that ever stops being true, the fix is a runtime type retry (below), not a second
registration.

## Why not registration-time firmware branching

`QuirkBuilder.firmware_version_filter(min_version=…, max_version=…)` **does exist** — upstream uses
it in `zhaquirks/innr/innr_sp240_plug.py` to split one SKU across firmware revisions — and on these
units it would read the right numbers: the OTA cluster's `current_file_version` is 129 and 132,
matching `app_version` exactly.

It is unusable here for a timing reason. ZHA only learns `current_file_version` when the **device
itself** sends a `query_next_image` (`zha/application/platforms/virtual.py`). Measured on these two
units: **1h14m and 1h40m after joining.** Quirks are matched at device initialisation, so at match
time the value is `None` and `allow_missing` decides. A filtered pair of registrations would
therefore always pick the wrong branch on first pairing and only correct itself after a restart,
stranding the first branch's entities as orphans — a worse first-run experience than an honest
error message.

Branching on Basic `app_version` via `.filter()` has the same defect: ZHA reads only
manufacturer_name and model_identifier at join, so `app_version` is usually uncached too.

## Why failing loudly is acceptable

The first draft rejected this option outright, on the grounds that the failure would be silent.
**That was wrong.** ZHA's `number` (and `select`) entities write through
`zha.application.helpers.write_attributes_safe`, which raises `ZHAException` on any non-SUCCESS
status record:

```python
raise ZHAException(f"Failed to write attribute {name}={value}: {record.status}")
```

Only the `zha.set_zigbee_cluster_attribute` **service** path swallows the status and reports
success — which is what the first draft measured and over-generalised from. Entity writes surface
the error to the user. Verified on hardware after this change shipped.

## Why not the alternatives

**A second quirk per firmware (rejected).** See the timing argument above.

**Runtime type retry for the backlight — write `enum8`, retry as `uint8` on `INVALID_DATA_TYPE`
(deferred, not rejected).** This is the only mechanism that can serve both revisions, and it needs
no firmware detection. It was deferred because it costs a failed round trip on every write for
whichever revision loses the coin flip, and because fw 129 is not a shipping concern today. It
remains the correct fix the moment it becomes one.

**Keeping the read-only sensors and documenting the limitation (rejected).** That was the status
quo and it is factually wrong for fw 132, where these are working controls that materially change
what the product does.

## Consequences

- **The cluster's contract is now "percent", for every writer.** `SimonDimmerLevelControl` converts
  in both `get()` and `write_attributes()`, so `zha.set_zigbee_cluster_attribute` on
  `min_level`/`max_level` now takes a percent too — passing a raw level there writes something else
  entirely. This is the same shape as the TS110D sibling.
- **`min > max` is refused by the quirk, not the device.** The device validates nothing: measured on
  fw 132, `min 200 / max 100` is stored without complaint and the running level jumps to 200. The
  guard raises `ZigbeeException` with a message naming which entity to move first, because with two
  coupled numbers the legal path depends on the order they are changed.
- **Entity bounds are static, so the guard cannot live in them.** ZHA takes a quirk's number
  min/max as fixed and cannot narrow one entity's range from the other's current value. Hence the
  1–100 % bounds plus a runtime check, rather than dynamic bounds.
- **Upgrading strands the old read-only sensors.** They share the new numbers' unique_ids but a
  different platform, so eight rows were left behind on the bench and removed with
  `config/entity_registry/remove`. Anyone upgrading an existing install needs the same sweep.
- **`app_version` is the only field that separates these units, and nothing in HA shows it.** Any
  support conversation about this SKU starts by asking for it.
- **A finding from one physical sample is not evidence about the model.** Sniffer findings in this
  repo that say "the device" should be read as "that unit" until a second sample agrees;
  `TS0052-FINDINGS.md`'s original conclusion was correct about V1 and wrong as a statement about
  TS0052.

## Corrections to the first draft

1. *"`QuirkBuilder` cannot express it. There is no `app_version` matcher."* — **False.**
   `firmware_version_filter` exists and reads the right values on these units. The real objection is
   that the value is not populated at match time.
2. *"`zha.set_zigbee_cluster_attribute` returns service success even when the device rejects the
   write … a fw-129 user would drag a slider, see no error, and see no effect."* — **True of the
   service path only.** Entity writes raise. The generalisation was drawn from a service-path
   measurement and it inverted the recommendation.

## Scope

Two samples, one SKU, one pair of firmware revisions. Whether other Tuya SKUs in this repo have the
same split is untested — the failure mode would have been invisible until now, because a single
sample per model cannot reveal it.
