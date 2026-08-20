---
status: accepted
date: 2026-08-20
---

# A Tuya datapoint write always reports success, so every DP control needs a read-back path

ADR 0003 accepted a deliberate trade — build to the newer firmware, let the older one *fail loudly* —
and rested it on a specific mechanism:

> ZHA's `number` (and `select`) entities write through `zha.application.helpers.write_attributes_safe`,
> which raises `ZHAException` on any non-SUCCESS status record.

That is true for standard ZCL attributes. **It is not true for Tuya datapoints**, and the difference
is invisible from the entity side. On 2026-08-20 a control that the device rejected outright
displayed its new value in Home Assistant without a murmur.

## What happens

`zhaquirks.tuya.mcu.TuyaMCUCluster.write_attributes()` does not wait for the device at all:

```python
async def write_attributes(self, attributes, manufacturer=UNDEFINED, **kwargs):
    """Defer attributes writing to the set_data tuya command."""
    await super().write_attributes(attributes, manufacturer=manufacturer, **kwargs)
    records = self._write_attr_records(attributes)
    for record in records:
        ...
        self.endpoint.device.command_bus.listener_event(TUYA_MCU_COMMAND, cluster_data)
    return [[foundation.WriteAttributesStatusRecord(foundation.Status.SUCCESS)]]
```

The DP frame is dispatched through a listener event — fire and forget — and the method returns a
hard-coded `SUCCESS`. `write_attributes_safe` sees SUCCESS and raises nothing. `tuya_mcu_command()`
then calls `cluster.update_attribute(...)` unconditionally, so the local attribute (and the HA
entity) takes the new value whatever the device thinks.

Measured on the 17-70E857TY (`_TZ3210_qe3d5gga`, app_version 134): writing Min Brightness through
the number entity left the entity reading `9` while the device had answered

```
DefaultResponse(command_id=0, status=<Status.UNSUP_CLUSTER_COMMAND: 129>)
```

— a total rejection. Nothing in the UI, the logbook, or the service response said so. Only
`zigpy.zcl` debug logging showed it.

## Decision

**Every Tuya-DP-backed control in this repo must have a read-back path, and the read-back is the
only acceptable evidence that a write worked.**

Concretely:

- When verifying a DP write by hand, read the value back from the device (a mirrored ZCL attribute,
  a `query_data` response, or an observable physical effect). A successful service call, a changed
  entity state, and an absent error message are all worthless as evidence here.
- When designing a DP control, prefer a device-side attribute that mirrors the DP as the source of
  truth for display. On the 70E857TY, LevelControl `min_level` (0x0002) is exactly that: read-only,
  rejects writes with `READ_ONLY 0x88`, but tracks the DP value live — writing DP 104 = 25 makes
  `min_level` read 25, writing 10 makes it read 10.
- Where no mirror exists, say so in the quirk docstring. A DP control with no read-back is a control
  that cannot be verified, and the next person needs to know that before they trust it.

## Why not fix it upstream

`write_attributes()` returning SUCCESS is not obviously a bug: the Tuya MCU protocol is
asynchronous, the device answers with its own `0x05`/`0x06` command rather than a write response,
and there is no general way to correlate an answer with the write that caused it. Changing the
return value would break every Tuya quirk that relies on optimistic state. The realistic mitigation
is the discipline above, not a patch.

## Consequences

- **ADR 0003's "failing loudly" standard is scoped to standard ZCL attributes.** It does not extend
  to Tuya DPs, and reasoning that assumes it does will be wrong in exactly the cases that matter.
- **A DP control's entity state is a *request*, not a *reading*** — unless it is fed by a mirror.
  On the 70E857TY the Min Brightness numbers read `unknown` after a restart until something writes
  them; that is honest behaviour and should not be "fixed" with a fabricated default.
- **This changes how these devices get debugged.** The first question about a Tuya control that
  "does nothing" is no longer "did the write fail?" but "did anyone ever confirm the write landed?"
