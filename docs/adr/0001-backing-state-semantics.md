# ADR 0001 — How a wrapped climate reads its backing entities

- Status: accepted
- Date: 2026-08-14
- Applies to: `custom_components/woow_zha_quirks/climate.py` (SM0308C / 8-58E7101,
  SM0308F / 14-66E7109TY, and every device added to `DEVICE_SPECS` after them)

## Context

`WoowClimate` owns no device state. Everything it shows is read back out of the Home
Assistant state machine from ZHA entities that some other integration creates, destroys and
recreates on its own schedule. That indirection is what makes the combined climate entity
possible, and it is also the only thing that has ever made it wrong.

Users reported that the 58E7101 climate "does not follow the actual device". Investigation
on the live sample server and then on 192.168.2.6 found three distinct defects, all of them
in this wrapper — not in the quirk and not in ZHA. Panel-side operations reach Home
Assistant in 2–5 ms and every enum maps correctly:

```
18:10:16.547 fan_mode=1 → select=low      18:10:24.045 system_mode=2 → select=Fan
18:11:56.121 fan_mode=5 → select=high     18:10:51.493 system_mode=0 → select=Cool
```

The three defects, each reproduced on 192.168.2.6 on 2026-08-13:

**Reports a running mode for a unit that is off.** `_state()` returned `None` for
"unavailable", "unknown" and "not in the state machine" alike, and `_recompute()` treated
`None` as "not off", falling through to the mode select:

```
18:31:38.886  recompute: backing={..., 'power':'unavailable'} -> hvac_mode=cool   ← unit is off
18:31:38.992  backing changed: switch...power -> off
18:31:38.992  recompute: backing={..., 'power':'off'}         -> hvac_mode=off    ← 106 ms later
```

The window exists because ZHA restores the OnOff switch *last*, after the selects and
sensors. It is short when the switch comes back, and unbounded when it does not.

**Serves a stale reading while the device is unreachable.** With every backing entity
explicitly `unavailable`, the entity still published a full, plausible, wrong state:

```
10:13:33.779  recompute: backing={temperature:'unavailable', mode:'unavailable',
                                  fan:'unavailable', preset:'unavailable',
                                  current_temp:'unavailable', power:'unavailable'}
           -> hvac_mode=fan_only fan=high target=26.0 current=24.1
```

**Misses a state-change delivery and never recovers.** At 10:13:40.658/.707/.768 the
backing entities were restored from `unavailable` to live values and the climate wrote
nothing at all; `last_reported` stayed at 10:12:57.809 for three minutes, until an unrelated
temperature report happened to arrive. Confirmed independently by the recorder and by a
5-second API poller. An identical trigger 18 minutes later was handled correctly, so this is
a race, not a deterministic path — which matches it occurring roughly once per three days in
the field. Nothing in the previous design would ever have recovered it: `should_poll` was
`False` and the state-change subscription was the only path in.

## Decision

**1. The power switch is the only authority on off-vs-running.** When it cannot be read,
`hvac_mode` is left unchanged. It is never inferred from the mode select.

**2. "Absent" and "unavailable" are different facts and stay separate.** `_raw()` returns
the literal state, or `None` when the entity is not in the state machine at all. Absence
means ZHA is rebuilding the entity — it lasts milliseconds, says nothing about the device,
and must not flap this entity. An explicit `unavailable` means ZHA has given up on the
device, and the climate reports `available = False` rather than a stale reading.
`_state()` keeps collapsing both to `None` for callers that only want a usable value.

**3. Only the roles that decide `hvac_mode` gate availability.** `ESSENTIAL_ROLES` is
`("power", "mode")`. Losing the fan select, the preset select, the setpoint number or the
temperature sensor keeps the last known value and leaves the entity available; a missing
temperature sensor is not a reason to take a working thermostat off the air.

**4. The subscription is a fast path, not a guarantee.** `SCAN_INTERVAL = 60 s` reconciles
against the backing entities; `async_update()` only re-runs `_recompute()`, reads nothing but
the HA state machine and produces no Zigbee traffic. This bounds staleness to 60 seconds
whatever happens to event delivery, and it gives operators a positive signal to check —
`last_reported` advances at least once a minute.

**5. The rebuild watchdog lives at platform level, not on the entity.**
`WATCHDOG_INTERVAL = 5 min` re-runs `_discover()`, which now verifies that the entity behind
the `created` guard is still in the state machine and drops the guard if it is not. An entity
that has vanished cannot poll itself back into existence, so this cannot hang off the entity.

## Consequences

- The climate can now be `unavailable`. That is a user-visible behaviour change: dashboards
  and automations that assumed the entity always has a mode need to tolerate it. This is the
  intended trade — an honest "unknown" beats a confident wrong answer for a device whose
  state drives heating and cooling.
- `iot_class` stays `local_push`. The poll carries no I/O; it is reconciliation, not polling
  the device.
- Worst-case staleness is now a number we can state and test (60 s) instead of "until the
  next unrelated event, if any".
- `tests/test_climate_recompute.py` locks the truth table in. Against the pre-fix code 10 of
  its 20 cases fail; the other 10 cover behaviour that was already correct.

## Alternatives considered

- **Only remove the fallthrough** (fix the wrong mode, leave the rest). Rejected: it fixes
  the visible symptom and leaves both the stale-while-unreachable reading and the unbounded
  freeze, which is the defect users actually reported.
- **Any backing entity unavailable ⇒ climate unavailable.** Rejected: one missing temperature
  sensor would take the whole thermostat off the air and break automations for no gain.
- **Chase the ZHA-side trigger instead.** The entity churn that exposes all this is worth
  understanding (see `docs/待排查問題.md`), but the wrapper must be correct regardless — the
  trigger may well live in panel firmware we do not control, and correctness cannot wait on
  that.
- **Re-resolve and re-subscribe on registry events.** Rejected as the primary mechanism: it
  addresses only one of the two failure shapes and needs the very event delivery that proved
  unreliable. The 60-second reconcile is both simpler and mechanism-agnostic.
