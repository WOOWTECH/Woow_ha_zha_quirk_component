---
status: superseded
date: 2026-08-12
superseded: 2026-08-13
---

# Volatile device settings are converged from a stored desired value in the integration layer

> **Superseded 2026-08-13.** The load-bearing assumption below was tested on the bench and does not
> hold: on the fw-129 unit `0x8001` neither drifts while powered nor resets across a power cycle,
> and the mode is genuinely applied after reboot. There is no loss to converge against, so the
> mechanism this ADR specifies would be a permanent no-op. Nothing downstream should be built on
> it. Evidence and full reasoning in **[Outcome](#outcome-2026-08-13--assumption-falsified)** at the
> foot of this file. The decision text is left intact as a record of what was decided and why.

Some Tuya firmware accepts and applies an Indicator Mode write, then loses it on a power cycle
(`docs/simon-product/241E8016TY-fw132-backlight-invalid-data-type.md`). The device does not report the
reset value, does not send a device announce, and ZHA never re-reads — so Home Assistant keeps showing
the pre-power-cycle value while the LED behaves differently. We decided to **persist the user's last
successfully written value in the custom component and periodically read the device, writing the value
back when the two differ**. The design deliberately keeps the desired value outside the zigpy attribute
cache, and deliberately never guesses a desired value the user has not expressed.

**This was `proposed`, not `accepted`, for one specific reason** — see *Load-bearing assumption*
below. That reason has since been tested and the assumption did not survive; see *Outcome*.

## Why the integration layer and not the quirk

A quirk is a stateless zigpy device definition: no `hass`, no `Store`, no timers, and
`QuirkBuilder` matches on manufacturer/model only — so it cannot hold a per-unit desired value nor
schedule anything. `relay_resync.py` already established the shape for exactly this failure mode
(device does not report its boot state, ZHA does not re-read) and this is the same mechanism with a
write added, so it belongs beside it.

A second constraint pushes the same way, and it is invisible in the code: **Home Assistant exposes no
service that reads a ZHA attribute.** `zha.set_zigbee_cluster_attribute` only writes, and
`homeassistant.update_entity` was measured to be a no-op on a ZHA config entity — after calling it,
the zigpy DB row's `last_updated` was unchanged, the state was unchanged, and no read frame appeared
in the bellows DEBUG stream. The read capability has to live inside our own code; there is no
external path to borrow.

## Why the desired value cannot live in the zigpy cache

Convergence needs a fresh read (`allow_cache=False`), and that read overwrites the zigpy cache with
device truth. Anything derived from the cache is therefore, by construction, the wrong side of the
comparison. The desired value goes in a `helpers.storage.Store`
(`woow_zha_quirks_config_resync`) keyed `{ieee: {endpoint: {attribute: int}}}`, holding **raw
integers only** — `CONTEXT.md` records that Indicator Mode integers differ between models even within
one Tuya model number, so a stored label would be a cross-model trap.

## How the desired value is captured

**Service-call cue plus delayed read-back adoption (chosen).** A `select.select_option` or
`zha.set_zigbee_cluster_attribute` call is treated only as *"someone touched this device"*; a few
seconds later we read `0x8001` and store **whatever the device now reports** as the desired value. The
desired value is therefore defined as *the last value the user successfully wrote*.

**Translating the select's label to an integer (rejected).** The label→integer mapping lives in eight
different per-model enum classes and the entity's `options` order is not guaranteed to equal the
attribute's integers. This is the exact trap `CONTEXT.md` warns about, and read-back adoption sidesteps
it entirely.

**Listening to the select's state changes (rejected).** Self-poisoning: our own convergence read
publishes device truth to the entity, which would then be adopted as the desired value — the mechanism
would erase its own intent on the first power cycle it was built to survive.

## Consequences

- **Firmware that rejects the write is handled by doing nothing special.** On app_version 132 the write
  fails with `INVALID_DATA_TYPE`, so read-back adoption stores the *old* value; desired equals actual,
  and convergence is a permanent no-op. Supporting fw 132's write encoding remains out of scope
  (quirk-layer work); a 3-consecutive-failure backoff per device exists only to stop log spam from any
  other write-rejecting unit, and logs once rather than every interval.
- **Untouched devices are never written to.** Detection is registry-driven (a ZHA select whose
  `unique_id` is `{ieee}-{endpoint}-backlight_mode`) rather than a model whitelist, so new quirks are
  covered without editing this module — the bench host already has 21 devices with a cached `0x8001`.
  But convergence only runs where a desired value was recorded, so a device the user has never
  configured in HA is read at most, never written. The cost of this choice is that Indicator Mode set
  *before* this feature shipped is not protected until the user sets it once more, or calls the service
  with `adopt`.
- **Home Assistant shows device truth, not the desired value.** After a power cycle the select briefly
  shows the reset value until the next convergence (≤5 min). Writing blind and never reading would look
  calmer, and was rejected precisely because it would let a rejected write masquerade as success.
- **Only endpoint 1 is converged.** `0x8001` is cached on up to four endpoints on some devices and the
  SM0502 disagrees across its own endpoints (`ep1=2, ep2=0`), but every quirk exposes the select on
  endpoint 1 only — the sole endpoint on which a user can express intent. Writing the other endpoints
  would be us inventing intent on the user's behalf.
- **Old four-segment unique_ids are ignored on purpose.** Six devices carry a legacy
  `{ieee}-1-6-backlight_mode` row alongside the modern three-segment one. All of them are
  `restored: True` and `unavailable` — dead rows from a previous quirk generation, still advertising
  stale labels (`LightWhenOn`/`LightWhenOff`), unclickable and therefore incapable of carrying intent.
  The cue parser matches the three-segment form strictly. Cleaning those rows is `orphan_sweep.py`'s
  job, not this module's.
- **Only Volatile Settings are converged — never Inert Settings.** `StartUpOnOff` (0x4003) and
  `StartUpCurrentLevel` (0x4000) on the same firmware family are ACKed, read back as the written value,
  and never applied at power-up; the quirks delete those entities rather than ship dead controls.
  Adding them to the convergence table would rewrite a setting the firmware ignores forever — busywork
  that looks like a fix. The distinction is recorded in `CONTEXT.md`.
- **The trigger set is inherited wholesale from `relay_resync.py`**: HA start, device-registry updates,
  and a 5-minute periodic backstop, skipping devices ZHA marks unavailable. Two other candidate
  triggers were rejected on evidence: these devices send no device announce after a power cycle, and
  ZHA's availability tracking needs roughly two hours of silence to flip a mains-powered device, so a
  30-second power cut never produces a transition to react to.

## Load-bearing assumption (why this was `proposed`)

The whole design assumes **the reset is caused by the power cycle**. The primary source is not
unambiguous on this point: it reports the fw-129 unit reverting from 2 back to 0 *"within a few minutes
with no ZHA write in between"* and reasons that this is *consistent with* the setting not surviving a
power cycle. If instead the value drifts while powered — a firmware timer, say — then periodic write-back
becomes an endless tug-of-war with the firmware, visible to the user as an LED that keeps changing, and
the correct product decision would be closer to "document it as read-only" than to converge harder.

This is settled before any write path is enabled, by a read-only build that samples `0x8001` once a
minute and appends to a JSONL file, with the unit parked at a non-default mode: **10 minutes** of clean
samples unblocks enabling write-back (that window covers the drift the source describes), **60 minutes**
unblocks release. If drift appears without a power cycle, this ADR is superseded rather than amended —
the decision it records would be wrong at the root, not merely mistuned.

## Outcome (2026-08-13) — assumption falsified

Tested on the fw-129 bench unit `8c:8b:48:ff:fe:d9:c6:d6` endpoint 1 with a read-only sampler
(`prototype/backlight-drift-sampler`, no write path), polling `0x8001` once a minute with
`allow_cache=False`. Parked 0 → 2 at 2026-08-12T10:58:07Z. Raw data and full write-up:
`docs/prototype/backlight-drift-{2026-08-12.jsonl,findings.md}` (1016 records).

1. **No drift while powered.** 922 consecutive samples over 15h25m, all `Mode_2` / `ok`, no value
   changes, no sampling gaps > 150s. This clears the 10-minute and 60-minute thresholds above by
   ~15x, and the "few minutes" the source describes by ~90x.
2. **No reset on power cycle.** A ~30s mains cut at ~02:23Z produced the only failed read in the
   whole run (`TimeoutError` at 02:23:23); the first read after restore returned **2** and held for
   32 further samples over 31 minutes. Corroborated by the recorder state jump on
   `light.241e8016ty_deng_guang` (unique_id `…c6:d6-1`). The device did genuinely reboot — it
   stopped answering, then reported a fresh boot state — so a RAM-only value would have been lost.
3. **The mode is applied, not merely stored.** Reading the attribute cannot distinguish an applied
   setting from an Inert one, so this was settled by eye: with a gang switched **off** the indicator
   LED was **lit**, which is `Switch_Position` (Mode_2) behaviour — Mode_0 would be dark and Mode_1
   never lights.

Indicator Mode on fw 129 is therefore an ordinary persistent setting: **neither Volatile nor
Inert**, and so in neither category this ADR was built around. Convergence would converge against a
loss that does not occur — desired would always equal actual and the mechanism would never write.

The primary source's observed 2 → 0 revert **did not reproduce** in 16+ hours and remains
unexplained. Candidates this test cannot distinguish: an unnoticed write (Tuya app, physical
long-press, another HA action), a different unit, a much longer outage, or a re-pair.
`docs/simon-product/241E8016TY-fw132-backlight-invalid-data-type.md` has been annotated accordingly.

**Scope.** One unit, one firmware, one attribute, one ~30s cut. A much longer outage was not tested.
fw 132 is untested by construction — it rejects the write, so it cannot be parked at a non-default
mode at all. Note that the ADR's own reasoning already made convergence a permanent no-op on fw 132
(read-back adoption stores the old value), so nothing is lost there either.

**What survives this ADR.** The two supporting observations still hold and are worth keeping
wherever they end up: Home Assistant exposes no service that reads a ZHA attribute
(`zha.set_zigbee_cluster_attribute` only writes; `homeassistant.update_entity` is a no-op on a ZHA
config entity), and the Volatile/Inert distinction for `StartUpOnOff` / `StartUpCurrentLevel` is
unaffected by this result.
