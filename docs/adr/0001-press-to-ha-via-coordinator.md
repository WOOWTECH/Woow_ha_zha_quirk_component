---
status: accepted
date: 2026-08-12
---

# Wall-panel presses reach other Zigbee devices via the coordinator, not device-to-device

A physical press on our Tuya scene panels drives other Zigbee devices by travelling
**panel → coordinator → HA automation → coordinator → target device**. We deliberately do *not*
bind or group the panels directly to their target devices, even though Zigbee supports it, because
the panel firmware makes direct binding useless: presses cannot be told apart at the target.

## Considered options

**Via the coordinator (chosen).** Each press arrives at the coordinator carrying the source
endpoint, so every gang is distinguishable and can drive a different HA automation. Everything runs
on the HA host and its radio — no WAN, no Tuya cloud, no gateway.

**Device-to-device (rejected).** Gateway sniffs (`docs/simon-product/7-12-gateway-full-sniff-findings.md`)
show that on press a panel also multicasts `Scenes RecallScene` — but **every gang multicasts to the
same group `0x270f` with the same scene `0xff`**. Target devices therefore cannot tell gang 1 from
gang 6, so a six-button panel collapses to one trigger. Plain binding is no better: the per-gang
press unicast is Tuya's private `OnOff` command `0xFB`, not a standard `Toggle`, so an ordinary
light bound to the panel simply ignores it. On top of that, each target device would need manual
`Groups AddGroup` + `Scenes AddScene` provisioning that ZHA exposes no UI for, redone whenever a
bulb is replaced.

The rejection is worth recording because "just bind the switch to the light, it's Zigbee" is the
obvious first suggestion and it is wrong here for a non-obvious reason.

## Consequences

- **WAN-independent.** No part of the path leaves the local network, so an internet outage does not
  affect it. This is verified by `docs/wan-outage-local-control-test.md`.
- **HA-host-dependent.** While HA is down, rebooting, or reloading ZHA, presses do nothing. This is
  the price paid for per-gang addressing, and it is the one thing device-to-device would have bought.
- **Two mechanisms coexist.** TS0034/TS0022 panels need Press Enablement before the firmware will
  transmit at all (`scene_activate.py`); TS0726 panels need nothing, because holding every gang in
  Switch Mode already produces an immediate report per press. Both end at the same coordinator, so
  the HA-side automation looks identical.
- **Scene Mode on TS0726 stays off.** It was evaluated in full and abandoned: it would cost the
  gang's indicator LED, has never been verified on TS0726 firmware, and buys nothing while only
  single-press triggering is required. Revisit only if multi-gesture presses become a requirement.
