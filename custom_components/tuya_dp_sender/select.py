"""Select entities for tuya_dp_sender.

Motor mode select for Tuya cover motor (DP106).
"""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tuya_dp_sender"

COVER_DEVICES = [
    {"ieee": "cc:86:ec:ff:fe:a1:ea:33", "name": "Tuya Cover"},
    {"ieee": "44:e2:f8:ff:fe:b7:34:33", "name": "Tuya Cover 2"},
]

MOTOR_MODE_OPTIONS = ["Linkage", "Inching"]
# DP106: 0=Linkage (连动模式), 1=Inching (点动模式)


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info=None
):
    if discovery_info is None:
        return
    entities = []
    for dev in COVER_DEVICES:
        entities.append(
            TuyaCoverMotorModeSelect(hass, dev["ieee"], dev["name"])
        )
    async_add_entities(entities)


class TuyaCoverMotorModeSelect(SelectEntity):
    """Select entity for Tuya cover motor mode (DP106)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cog-transfer"
    _attr_has_entity_name = False
    _attr_options = MOTOR_MODE_OPTIONS

    def __init__(self, hass, ieee, device_name):
        self.hass = hass
        self._ieee = ieee
        self._attr_name = f"{device_name} Motor Mode"
        self._attr_unique_id = f"tuya_cover_motor_mode_{ieee.replace(':', '')}"
        self._attr_current_option = MOTOR_MODE_OPTIONS[0]  # default Linkage

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        try:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={("zha", self._ieee)})
            if device is not None:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, device_id=device.id)
        except Exception as exc:
            _LOGGER.warning("Failed to link select to ZHA device: %s", exc)

    async def async_select_option(self, option: str):
        """Send ENUM DP106 command."""
        value = MOTOR_MODE_OPTIONS.index(option)  # 0=Linkage, 1=Inching
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
                "dp": 106,
                "dp_type": 4,   # ENUM
                "value": value,
            }})()
        )
        self._attr_current_option = option
        self.async_write_ha_state()
        _LOGGER.info("Motor mode set to %s (DP106=%d) on %s", option, value, self._ieee)
