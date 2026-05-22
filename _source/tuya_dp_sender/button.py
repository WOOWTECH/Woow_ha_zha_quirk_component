"""Button entities for tuya_dp_sender.

Momentary-action buttons for Tuya cover motor settings (DP101-105).
These send a BOOL=true DP command to trigger the action.
"""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tuya_dp_sender"

# All cover devices that need DP101-105 buttons
COVER_DEVICES = [
    {"ieee": "cc:86:ec:ff:fe:a1:ea:33", "name": "Tuya Cover"},
    {"ieee": "44:e2:f8:ff:fe:b7:34:33", "name": "Tuya Cover 2"},
]

# Each button: (dp, unique_suffix, name, icon)
COVER_BUTTONS = [
    (101, "remote_register", "Remote Register", "mdi:remote"),
    (102, "reset_limit", "Reset All Limits", "mdi:restart"),
    (103, "upper_limit", "Upper Limit Set/Reset", "mdi:arrow-collapse-up"),
    (104, "middle_limit", "Middle Limit Set/Reset", "mdi:arrow-collapse-vertical"),
    (105, "lower_limit", "Lower Limit Set/Reset", "mdi:arrow-collapse-down"),
]


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info=None
):
    if discovery_info is None:
        return
    entities = []
    for dev in COVER_DEVICES:
        for dp, suffix, name, icon in COVER_BUTTONS:
            entities.append(
                TuyaCoverButton(hass, dev["ieee"], dev["name"], dp, suffix, name, icon)
            )
    async_add_entities(entities)


class TuyaCoverButton(ButtonEntity):
    """Button that sends a BOOL=true DP command (momentary toggle)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = False

    def __init__(self, hass, ieee, device_name, dp, suffix, name, icon):
        self.hass = hass
        self._ieee = ieee
        self._dp = dp
        self._attr_name = f"{device_name} {name}"
        self._attr_unique_id = f"tuya_cover_{suffix}_{ieee.replace(':', '')}"
        self._attr_icon = icon

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        try:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={("zha", self._ieee)})
            if device is not None:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, device_id=device.id)
        except Exception as exc:
            _LOGGER.warning("Failed to link button to ZHA device: %s", exc)

    async def async_press(self):
        """Send BOOL DP=true to trigger the action."""
        data = self.hass.data.get(DOMAIN)
        if data is None:
            _LOGGER.error("tuya_dp_sender not loaded")
            return
        handle = data.get("handle_send_dp")
        if handle is None:
            _LOGGER.error("handle_send_dp not available")
            return
        await handle(
            type("FakeCall", (), {"data": {
                "ieee": self._ieee,
                "dp": self._dp,
                "dp_type": 1,   # BOOL
                "value": 1,     # true
            }})()
        )
        _LOGGER.info("Button pressed: DP%d=true on %s", self._dp, self._ieee)
