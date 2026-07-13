"""Keep woow v2 quirks authoritative when upstream zhaquirks ships a competing v2 quirk.

zigpy's v2 registry resolves a device with ``DeviceRegistry.get_device()``, which returns the
**first matching entry** in ``_registry_v2[(manufacturer, model)]``. Entries are inserted with
``add_to_registry_v2()`` using ``deque.appendleft`` (newest-first), so the quirk that registers
*last* wins.

The woow component registers all its quirks at **import time** (see ``__init__._load_quirks``),
which runs before ZHA calls ``zhaquirks.setup()`` during gateway startup. A woow quirk therefore
starts at the front of the deque — but when upstream registers a **v2** quirk for the same
signature during ``zhaquirks.setup()``, its ``appendleft`` jumps ahead and upstream wins.
(Upstream **v1** quirks are never a problem: ``get_device`` tries all v2 quirks before any v1.)

The first device to hit this was ``_TZE204_clrdrnya`` (WO_40117): upstream ``zhaquirks.tuya
.tuya_motion`` has a full v2 builder for it, so the woow quirk was silently shadowed.

Fix: install a one-time guard on ``add_to_registry_v2`` so that, for any ``(manufacturer, model)``
key a woow quirk already owns, a later **non-woow** entry is appended to the **back** of the deque
instead of the front. The woow quirk stays the winner — deterministically, on every boot, with no
ZHA reload. Signatures owned only by upstream are left completely untouched.
"""

from __future__ import annotations

import logging

from zigpy.quirks.registry import DeviceRegistry

_LOGGER = logging.getLogger(__name__)

_GUARD_INSTALLED_FLAG = "_woow_priority_guard_installed"
_WOOW_MARKER = "woow_zha_quirks"


def _is_woow_entry(entry: object) -> bool:
    """True if a registry entry originates from a woow_zha_quirks quirk file."""
    return _WOOW_MARKER in str(getattr(entry, "quirk_file", "") or "")


def install_priority_guard() -> None:
    """Patch ``DeviceRegistry.add_to_registry_v2`` to keep woow quirks in front.

    Idempotent — safe to call more than once. Must be called *after* the woow quirks have
    registered (so the relevant keys are already woow-owned), which ``__init__`` guarantees by
    calling this right after ``_load_quirks()``.
    """
    if getattr(DeviceRegistry, _GUARD_INSTALLED_FLAG, False):
        return

    original_add = DeviceRegistry.add_to_registry_v2

    def _guarded_add(self, manufacturer, model, entry):
        key = (manufacturer, model)
        existing = self._registry_v2.get(key)
        if existing and not _is_woow_entry(entry) and any(
            _is_woow_entry(e) for e in existing
        ):
            # A woow quirk owns this signature. Demote the competing (upstream) entry to the
            # back of the deque so the woow entry stays first and wins get_device().
            self._registry_v2[key].append(entry)
            _LOGGER.info(
                "WOOW ZHA Quirks: kept woow quirk authoritative for %s "
                "(demoted competing %s)",
                key,
                getattr(entry, "quirk_file", "?"),
            )
        else:
            original_add(self, manufacturer, model, entry)

    DeviceRegistry.add_to_registry_v2 = _guarded_add
    setattr(DeviceRegistry, _GUARD_INSTALLED_FLAG, True)
    _LOGGER.info("WOOW ZHA Quirks: v2 quirk-priority guard installed")
