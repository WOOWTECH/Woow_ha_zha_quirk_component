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

### Device shape

**Quirk**:
A zigpy device definition that corrects or extends how ZHA interprets a specific
manufacturer/model, keyed on the pair of the two.
_Avoid_: device handler, custom device

**Datapoint (DP)**:
A numbered value in Tuya's private MCU protocol (cluster 0xEF00). Tuya's own documentation is
written in DPs, so DP numbers are the bridge between Tuya docs and Zigbee clusters — but a DP
existing does not mean the device reports it.
_Avoid_: attribute (that word belongs to ZCL)

**Phantom Endpoint**:
An endpoint a device advertises that drives no physical hardware. Removed by the quirk so it does
not produce a dead entity.
_Avoid_: ghost endpoint, unused endpoint
