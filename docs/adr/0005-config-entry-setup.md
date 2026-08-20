---
status: accepted
date: 2026-08-20
---

# Setup moves to a config entry, but the quirks it installs are not part of that entry's lifecycle

- Applies to: `custom_components/woow_zha_quirks/__init__.py`, `config_flow.py`, `const.py`,
  `manifest.json`, and every `async_setup_*` hook module (`knob_rebind`, `relay_resync`,
  `scene_activate`, `light_effects`, `presence_defaults`, `quirk_heal`, `orphan_sweep`)
- Supersedes: the `woow_zha_quirks:` key in `configuration.yaml` (removed in 1.4.0)

## Context

Up to 1.3.1 this integration was set up by a bare `woow_zha_quirks:` line in
`configuration.yaml`. It carried no options and never had a `CONFIG_SCHEMA`: the key existed
only to make Home Assistant import the package. Home Assistant has been steering every
integration to config entries for years, and a YAML-only integration is increasingly the odd
one out — no UI presence, no reload button, no way to remove it without editing a file.

Moving to a config entry is straightforward for a normal integration, whose effects all live
inside `async_setup_entry` and can be undone in `async_unload_entry`. This integration is not
normal. Its primary effect is **process-global and irreversible**:

- `__init__._load_quirks()` registers ~35 quirks into the v2 quirk registry at **module-import
  time**, not during setup. zigpy/ZHA offer no unregister.
- `quirk_priority.install_priority_guard()` monkey-patches `DeviceRegistry.register` (or the
  legacy `add_to_registry_v2`) so that a later non-woow entry for a signature woow already owns
  is dropped rather than reordered.
- `light_effects._apply_patch()` monkey-patches the ZHA `Light` class, keeping the original
  callables in closures. It is idempotent but not revertible.

None of the three can be undone by unloading a config entry. So the migration is not "wrap the
existing setup in an entry"; it is a decision about which parts of this integration belong to an
entry's lifecycle and which parts simply do not.

Three sub-decisions follow from that single tension, and they are recorded together here because
splitting them would produce three documents that only cross-reference each other.

## Decision 1 — Hard cut: the YAML key stops working, with a one-click repair as the bridge

1.4.0 removes YAML setup outright. There is no `SOURCE_IMPORT` flow that silently converts an
existing YAML install into a config entry.

The consequence is real and must not be understated: **after upgrading, a machine whose owner
does nothing has no config entry, so Home Assistant does not set the component up, so the
runtime hooks and the climate entities do not exist.** Users must add the integration from the
UI once.

To keep that from becoming a silent breakage, a deliberately minimal `async_setup` is retained
for exactly two jobs:

- `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`, so a leftover key produces Home
  Assistant's standard "configured via the UI, YAML ignored" warning instead of an obscure one.
- If the leftover key is present, raise a **fixable repair issue** whose fix flow
  (`ConfirmRepairFlow`) creates the config entry. Two clicks, from the dashboard, no file editing.

A leftover YAML key is what makes this hook reachable at all: the domain appearing in
`configuration.yaml` is what causes Home Assistant to import the package in the absence of an
entry. That import still registers the quirks, so a user who upgrades and touches nothing keeps
working quirks — they lose only the hook modules and the climate entities until they accept the
repair. Users who already removed the key and have no entry get nothing: no import, no hook, no
notification. That gap is inherent to a hard cut and is covered only by the release notes.

### Why not an import flow

An import flow was considered and rejected by the maintainer: an upgrade that rewrites a user's
configuration into a config entry with no interaction hides a breaking change rather than
communicating it. The repair issue keeps the migration explicit — a human accepts it — while
removing the "my devices broke and I have no idea where to click" failure mode.

### When the YAML detection can be removed

The `async_setup` / `CONFIG_SCHEMA` / repair-issue block exists only for the 1.3.x → 1.4.0
migration. It can be deleted once no supported install is expected to still carry the key —
proposed trigger: the second minor release after 1.4.0, or any 2.x.

## Decision 2 — `manifest.json` declares no dependency on `zha`, and this must stay that way

`manifest.json` gains `"config_flow": true` and `"single_config_entry": true`. It gains
**neither `dependencies` nor `after_dependencies`** on `zha`, even though this integration is
useless without ZHA and even though every reviewer's instinct is to add one.

The reason is the quirk-priority mechanism. The v2 registry resolves a device to the *first*
matching entry for its `(manufacturer, model)` key and inserts newest-first, so **the quirk that
registers last wins**. woow registers at import time and immediately installs the priority
guard; the guard drops *subsequent* non-woow registrations for keys woow already owns. ZHA
registers the upstream `zhaquirks` set later, when its gateway starts during its own config
entry setup. The whole scheme therefore depends on **woow being imported before ZHA's gateway
startup**.

Both `dependencies` and `after_dependencies` do the same thing to load order: they force ZHA to
be set up *first*. That is precisely the ordering in which the guard is installed too late and
upstream wins — the ordering that shipped `_TZE204_clrdrnya` (WO_40117) with
`zhaquirks.tuya.tuya_motion`'s builder silently shadowing the woow quirk. This is not a
prediction; it is recorded in `quirk_heal.py` and was paid for in commit `81cd348`.

The move to a config entry does **not** change this race in either direction. Under both YAML and
config entries the package is imported inside `async_setup_component(domain)`, before
`async_setup_entry` runs. `quirk_heal.py` remains the safety net for the boots where the race is
lost, and `const.py` (below) removes the one new import path a config flow would otherwise add.

### `const.py`

`DOMAIN` and friends move to `const.py`, and `config_flow.py` imports only from there. Without
that split, Home Assistant importing `config_flow.py` — which happens merely to render the
"add integration" list — would drag in the package `__init__` and register 35 quirks plus a
registry monkey-patch as a side effect of browsing a UI list.

### Why not make the priority guard retroactive

Rewriting `install_priority_guard()` to also sweep already-registered entries would make load
order irrelevant for the *priority* half of the race. It was rejected for this change: it fixes
only half (ZHA having already built device objects still needs `quirk_heal`'s reload), and it
means reaching further into registry internals that `quirk_priority.py` already has to
straddle across two ZHA versions. It belongs in its own issue, not in a setup-mechanism change.

## Decision 3 — Unloading an entry never revokes a global side effect

`async_unload_entry` is implemented, so the reload button works. It tears down exactly what
belongs to the entry:

- the `climate` platform (via `async_forward_entry_setups` / `async_unload_platforms`),
- all 16 listeners, timers and `async_at_start` hooks the seven hook modules register, and
- the four services.

To make that possible, every hook module takes the `ConfigEntry` and registers through
`entry.async_on_unload(...)`. Today those 16 registrations keep no unsubscribe handle at all,
which is harmless only because setup happens once per process; with a reload button it would
mean a second `orphan_sweep` (which deletes entity registry rows) and a second
`presence_defaults` (which writes device settings) running alongside the first.

The four services move from module-level registration to the entry, and are removed on unload.
A service that exists without the entry that backs it would accept calls and do nothing.
`relay_resync`'s service — currently registered but missing from `services.yaml` — is documented
as part of this change.

What unload does **not** do: unregister quirks, uninstall the priority guard, or revert the
`light_effects` patch. All three stay for the life of the process, and the log says so.

Because "I removed the integration and my devices are still quirked" is a support call waiting
to happen, `async_remove_entry` raises a one-off persistent notification stating that a Home
Assistant restart is required to fully remove the quirks. A notification, not a repair issue:
there is no button that can fix it, and a repair issue implies there is.

### Entity identity

The climate platform moves from discovery (`async_load_platform` → `async_setup_platform`) to
`async_forward_entry_setups`. Unique IDs are **unchanged**, so the existing entity registry rows
are re-pointed at the new config entry rather than replaced. This is the one part of the change
that can make something visibly disappear — the live host already shows `climate.58e7101_2` and
`climate.66e7109ty_2`, whose `_2` suffixes suggest older rows for the same devices — and it is
verified on hardware rather than by reasoning (see Scope).

## Consequences

- **Breaking.** 1.4.0 requires a manual step on every existing install. Release notes lead with
  `⚠️ BREAKING`, because the HACS update dialog is the only text a user reads before updating.
- The integration gains a UI presence, a reload button, and a removal path it never had.
- Reloading becomes safe for the first time: no duplicate registry sweeps, no duplicate device
  writes.
- Removal is still only partially effective until restart, and now says so.
- Anyone later "fixing" the missing `zha` dependency in `manifest.json` will silently reintroduce
  a bug that has already shipped once. That is the single most likely way for this decision to be
  undone, which is why it has a section of its own here and a pointer from `quirk_heal.py`.

## Scope

Out of scope, deliberately: an options flow or per-hook enable/disable toggles; making the
priority guard retroactive; translating the four services' names and descriptions; and any
change to quirk behaviour. `hacs.json`'s `homeassistant: 2026.3.0` floor stays — the legacy
registry branch in `quirk_priority.py` still supports it — even though the reference host runs
2026.7.2.

Verification is on the live ZHA host (192.168.2.6, HA 2026.7.2, 39 paired devices), before and
after deploy, with a `cp -a` backup of `d311a22` kept until it passes:

1. `quirk_applied` for all 39 devices. Baseline: only the coordinator and `_TZ3210_ey6yyb25`
   (SP9-200-14) are unquirked, the latter only because the host runs 1.3.0 and the quirk file is
   absent — deploying restores it.
2. For the 10 devices reporting `quirk_class = zhaquirks.tuya.builder`, the registry `source.file`
   must still point at `woow_zha_quirks`. `quirk_applied` alone cannot detect upstream winning.
3. Entity-id set diff (nothing vanished, nothing renamed) and the four services present.
4. `climate.58e7101_2` and `climate.66e7109ty_2` driven for real — hvac_mode, target temperature,
   fan_mode — each read back to confirm the backing entities follow, then restored to `off`.
   A read-only check cannot see the wrapper/backing linkage, which is where every defect in
   ADR 0001 lived.
