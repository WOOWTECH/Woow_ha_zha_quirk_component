# WOOW ZHA Quirks

A Home Assistant custom integration that ships ZHA quirks (plus a few runtime hooks) for Tuya-based
Simon / WOOW Zigbee devices, so they work fully locally through ZHA instead of through a Tuya
gateway. This glossary exists mainly because the word "scene" means four unrelated things in this
domain, and conflating them has already caused wrong conclusions.

## Language

### The four meanings of "scene"

Always qualify the word. Bare "scene" is banned in code comments and docs.

**ZCL Scene**:
A scene stored in a device's Zigbee Scenes cluster (0x0005), identified by a group id plus a scene
id. In this project it is never used to store attribute values.
_Avoid_: scene, zigbee scene

**Press Enablement**:
The handshake that makes a Tuya scene panel willing to transmit a physical press at all — storing a
ZCL Scene in a group the device belongs to. The stored scene is a token, not a scene; it is never
recalled.
_Avoid_: scene activation, scene storage

**Tuya App Scene**:
An automation rule living in the Tuya gateway or Tuya cloud. Outside this project's control and
unreachable once a device is paired to ZHA.
_Avoid_: cloud scene, tuya automation

**HA Automation**:
A Home Assistant automation, script, or scene entity. The only place this project puts
press-to-action logic.
_Avoid_: HA scene (ambiguous with the above)

### Panels and buttons

**Gang**:
One button position on a multi-button wall panel, backed by its own Zigbee endpoint.
_Avoid_: channel, button, position, key

**Gang Mode**:
A per-gang firmware setting on TS0726 panels (attribute 0xD020 on cluster 0xE001) selecting whether
that gang behaves as a Switch or as a Scene trigger. Its integer values are inverted between the two
TS0726 variants we support.
_Avoid_: switch mode (collides with the value below), button mode

**Switch Mode**:
The Gang Mode value in which a press flips the gang's own on/off state. The state change is what
forces the firmware to report immediately.
_Avoid_: relay mode

**Scene Mode**:
The Gang Mode value in which a press does not change the gang's on/off state. Presses produce no
usable Zigbee frame under ZHA.
_Avoid_: trigger mode, event mode

**Internal Latch**:
The firmware's on/off state for a gang on a panel that has no load output terminals. It is what
Switch Mode toggles on those panels — there is no wired contact to switch.
_Avoid_: relay (wrong on load-less panels, and the error has misled us before)

**Press Signal**:
Whatever a device actually puts on the air when a physical button is pressed. Differs by model: an
on/off attribute report, a Tuya `0xFB` command, or a group multicast.
_Avoid_: button event, press event

**Indicator Mode**:
A panel's backlight LED behaviour setting (attribute 0x8001 on cluster 0x0006). Its integer values
differ between models even within one Tuya model number.
_Avoid_: backlight mode, LED mode

### Settings that do not stick

Three firmware failures look identical from Home Assistant — a setting that "does not work" — and
they have different remedies. Never say a setting is "not saved" without saying which of these it is.
Misclassifying one of these as another has already cost this project a wrong conclusion and a
feature that was removed while it was in fact working.

**Volatile Setting**:
A device setting the firmware accepts and genuinely applies, then discards on a power cycle — without
reporting the reset and without announcing its return. Only Volatile Settings are worth converging.
_Avoid_: non-persistent setting, transient setting

**Inert Setting**:
A device setting the firmware accepts and reads back as the written value, but never acts on
(`StartUpOnOff` on several of our devices). The remedy is to remove the control, not to write it
again; writing it repeatedly is busywork that looks like a fix. Before calling anything inert, rule
out an Uncommitted Setting: the two are indistinguishable from the traffic alone, and only one of
them justifies removing the control.
_Avoid_: broken setting, unsupported attribute — the attribute is supported, it is merely ignored

**Uncommitted Setting**:
A device setting whose stored value and acted-on value are two different things inside the firmware.
A write updates the stored one — SUCCESS, an echoed report, a correct read-back, survival across a
mains power cycle — while the device keeps acting on the value it last committed. The remedy is to
satisfy the Commit Condition, not to remove the control.
_Avoid_: inert setting (opposite remedy), not saved, ignored write

**Commit Condition**:
What a write must satisfy before the firmware replaces the committed value with the stored one. It is
device-specific, undocumented, and found by comparing our traffic against a Tuya gateway's: on the
66E8015 dimmer, min and max brightness must arrive within about a second of each other. A control
backed by an Uncommitted Setting is only correct once its quirk guarantees this.
_Avoid_: magic spell (that is a join-time handshake, a different thing), activation

**Read-Back Trap**:
Concluding that a setting works because the device returns the value that was written. On an
Uncommitted Setting the read reports storage, so it agrees with the write no matter what the device
is actually doing. The only honest test is to make the device act and observe the result.
_Avoid_: verified, confirmed stored — say which of the two was confirmed

**Desired Indicator Mode**:
The Indicator Mode value the user last successfully wrote, remembered separately from whatever the
device currently reports. It is the only record of user intent: the device's own value cannot stand in
for it, because reading the device replaces what it would have told us.
_Avoid_: expected value, target mode, cached value

**Convergence**:
One round of reading a Volatile Setting's true value from a device, comparing it against the desired
value, and writing the desired value back when the two differ. Reading is part of the definition — a
mechanism that only writes cannot tell a successful write from a silently rejected one.
_Avoid_: sync, restore, re-apply

**Adopt**:
To record a device's current value as the desired value. Happens both when the user changes a setting
(the new value is read back from the device and adopted) and when an already-configured device's
existing value should be taken as intent.
_Avoid_: learn, capture

### Device shape

**Quirk**:
A zigpy device definition that corrects or extends how ZHA interprets a specific
manufacturer/model, keyed on the pair of the two.
_Avoid_: device handler, custom device

**Datapoint (DP)**:
A numbered value in Tuya's own model of a device, as the cloud and the app see it. Tuya's
documentation, the cloud API and the app are all written in DPs, so DP numbers are the bridge
between Tuya's world and Zigbee — but a DP existing does not mean the device reports it, and it
says nothing about how the value travels over the air. That is the DP Carrier.
_Avoid_: attribute (that word belongs to ZCL); "0xEF00 value" (only one of the carriers)

**DP Carrier**:
How a DP is actually transmitted on the air. Two are in use here: Tuya's private MCU protocol on
cluster 0xEF00, or a manufacturer-reserved command or attribute on an otherwise standard cluster.
The SP9-200-14 driver has an 0xEF00 cluster and uses **none** of it for its DPs — brightness rides
a Level cluster command, colour temperature a Color cluster command. Knowing a DP number tells you
nothing about its carrier, and mistaking the two has already cost this project a wrong conclusion:
`16-SP9-200-10-sniff-findings.md` read a work_mode command as an end-of-drag marker.
_Avoid_: transport, encoding, DP mapping

**Phantom Endpoint**:
An endpoint a device advertises that drives no physical hardware. Removed by the quirk so it does
not produce a dead entity.
_Avoid_: ghost endpoint, unused endpoint
