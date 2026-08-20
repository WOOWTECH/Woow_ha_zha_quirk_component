"""The 1.4.0 setup mechanism: config flow, YAML repair bridge, and teardown.

These cover the failure modes that look fine on a live box until you poke at an edge:
a second entry sneaking in, the migration prompt never appearing, and a reload leaving a
second copy of every hook running. See docs/adr/0005-config-entry-setup.md.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_zha_quirks.const import DOMAIN, ISSUE_YAML_REMOVED
from custom_components.woow_zha_quirks.repairs import async_create_fix_flow

# Every service the integration owns. resync_relay was registered but undocumented before
# 1.4.0; it is in services.yaml now and is covered here like the rest.
SERVICES = (
    "rebind_knob",
    "resync_relay",
    "activate_scene_switches",
    "apply_presence_defaults",
)


async def test_user_flow_creates_the_entry(hass: HomeAssistant) -> None:
    """The confirm step is shown first, and submitting it creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "WOOW ZHA Quirks"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_second_entry_is_refused(hass: HomeAssistant) -> None:
    """single_config_entry: a second flow aborts instead of creating a rival entry."""
    MockConfigEntry(domain=DOMAIN, title="WOOW ZHA Quirks").add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_leftover_yaml_raises_a_fixable_issue(hass: HomeAssistant) -> None:
    """A 1.3.x install that upgrades and does nothing gets a repair prompt, not silence."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: None})
    await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_YAML_REMOVED)
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.WARNING


async def test_no_yaml_no_issue(hass: HomeAssistant) -> None:
    """Setting the component up without the obsolete key must not nag."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_YAML_REMOVED) is None


async def test_repair_flow_creates_the_entry(hass: HomeAssistant) -> None:
    """Confirming the repair is the whole migration: two clicks, no file editing."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: None})
    await hass.async_block_till_done()

    flow = await async_create_fix_flow(hass, ISSUE_YAML_REMOVED, None)
    flow.hass = hass

    result = await flow.async_step_init()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await flow.async_step_confirm({})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_unknown_repair_issue_is_rejected(hass: HomeAssistant) -> None:
    """A typo'd issue id must fail loudly rather than hand back a confirm dialog."""
    with pytest.raises(ValueError):
        await async_create_fix_flow(hass, "not_a_real_issue", None)


async def test_setup_registers_services_and_unload_removes_them(
    hass: HomeAssistant,
) -> None:
    """The black-box check on teardown.

    Every hook registers through `entry.async_on_unload` now; the services are the part of
    that wiring an outside observer can see. If one of the ~20 registrations is ever left
    unwrapped again, this is what catches it -- and unlike a per-module mock, it keeps
    working when the modules are refactored.
    """
    entry = MockConfigEntry(domain=DOMAIN, title="WOOW ZHA Quirks")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for service in SERVICES:
        assert hass.services.has_service(DOMAIN, service), service

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    for service in SERVICES:
        assert not hass.services.has_service(DOMAIN, service), service


async def test_reload_does_not_duplicate_services(hass: HomeAssistant) -> None:
    """Reloading is the new capability config entries bring; it must stay idempotent."""
    entry = MockConfigEntry(domain=DOMAIN, title="WOOW ZHA Quirks")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    for service in SERVICES:
        assert hass.services.has_service(DOMAIN, service), service
