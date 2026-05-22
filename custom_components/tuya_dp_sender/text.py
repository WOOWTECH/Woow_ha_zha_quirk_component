"""Text entities for Tuya switch screen labels (DP 105-108).

Each text entity allows the user to type a label for the
corresponding switch channel. When changed, the string is sent
to the device by constructing a TuyaCommand with TuyaDatapointData
directly, bypassing write_attributes (which has a type-cast bug
for string values in TuyaClusterData).
"""
import logging

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tuya_dp_sender"

# IEEE of the 4-gang switch
SWITCH_IEEE = "a4:c1:38:0c:bc:72:be:6d"

LABEL_DPS = [
    {"dp": 105, "channel": 1, "attr": "screen_label_1", "default": "Switch 1"},
    {"dp": 106, "channel": 2, "attr": "screen_label_2", "default": "Switch 2"},
    {"dp": 107, "channel": 3, "attr": "screen_label_3", "default": "Switch 3"},
    {"dp": 108, "channel": 4, "attr": "screen_label_4", "default": "Switch 4"},
]


async def _get_tuya_cluster(hass, ieee_str):
    """Get the Tuya MCU cluster (0xEF00) for a device by IEEE address."""
    gateway = None
    zha = hass.data.get("zha")
    if zha is not None:
        if isinstance(zha, dict):
            for v in zha.values():
                if hasattr(v, "application_controller"):
                    gateway = v
                    break
                if hasattr(v, "gateway"):
                    gateway = getattr(v, "gateway")
                    break
        else:
            if hasattr(zha, "gateway_proxy"):
                gateway = zha.gateway_proxy.gateway
            elif hasattr(zha, "gateway"):
                gateway = zha.gateway
            elif hasattr(zha, "application_controller"):
                gateway = zha

    if gateway is None:
        try:
            from homeassistant.components.zha.helpers import get_zha_gateway
            gateway = get_zha_gateway(hass)
        except Exception:
            pass

    if gateway is None:
        _LOGGER.error("ZHA gateway not found")
        return None

    app = gateway.application_controller
    norm = ieee_str.lower().replace(":", "")
    device = None
    for dev in app.devices.values():
        if str(dev.ieee).lower().replace(":", "") == norm:
            device = dev
            break

    if device is None:
        _LOGGER.error("Device %s not found", ieee_str)
        return None

    ep = device.endpoints.get(1)
    if ep is None:
        _LOGGER.error("Endpoint 1 not found on %s", ieee_str)
        return None

    cluster = ep.in_clusters.get(0xEF00)
    if cluster is None:
        _LOGGER.error("Tuya cluster 0xEF00 not found on %s", ieee_str)
        return None

    return cluster


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info=None
):
    if discovery_info is None:
        return
    entities = []
    for item in LABEL_DPS:
        entities.append(
            TuyaSwitchLabelText(
                hass, SWITCH_IEEE,
                item["dp"], item["channel"], item["attr"], item["default"],
            )
        )
    async_add_entities(entities)


class TuyaSwitchLabelText(TextEntity, RestoreEntity):
    """Text entity for a Tuya switch screen label."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:label-outline"
    _attr_has_entity_name = False
    _attr_native_min = 0
    _attr_native_max = 12

    def __init__(self, hass, ieee, dp, channel, attr_name, default):
        self.hass = hass
        self._ieee = ieee
        self._dp = dp
        self._channel = channel
        self._attr_name_tuya = attr_name  # e.g. "screen_label_1"
        self._attr_name = f"Switch {channel} Screen Label"
        self._attr_unique_id = f"tuya_label_{ieee.replace(':', '')}_{dp}"
        self._attr_native_value = default

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # Restore previous value
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last_state.state

        # Link to ZHA device
        try:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={("zha", self._ieee)})
            if device is not None:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, device_id=device.id)
        except Exception as exc:
            _LOGGER.warning("Failed to link to ZHA device: %s", exc)

    async def async_set_value(self, value: str) -> None:
        """Set the label value and send to device.

        Bypasses write_attributes (TuyaClusterData.attr_value is typed
        as int, which breaks string values). Instead, we construct a
        TuyaCommand with TuyaDatapointData directly and send via
        cluster.command(0x00, ...).
        """
        self._attr_native_value = value
        self.async_write_ha_state()

        cluster = await _get_tuya_cluster(self.hass, self._ieee)
        if cluster is None:
            _LOGGER.error("Cannot send label: TuyaMCU cluster not found")
            return

        try:
            from zhaquirks.tuya import (
                TuyaCommand, TuyaDatapointData, TuyaData, TuyaDPType,
            )
            import zigpy.types as t

            # Z2M sends name DPs as RAW (dp_type=0x00) with UTF-8 bytes,
            # NOT as STRING (dp_type=0x03). Truncate to 12 chars per Z2M.
            limited = value[:12]
            tuya_data = TuyaData()
            tuya_data.dp_type = TuyaDPType.RAW
            tuya_data.raw = limited.encode("utf-8")

            # Build TuyaDatapointData
            dpd = TuyaDatapointData(self._dp, tuya_data)

            # Build TuyaCommand
            cmd = TuyaCommand()
            cmd.status = 0
            cmd.tsn = cluster.endpoint.device.application.get_sequence()
            cmd.datapoints = t.List([dpd])

            # Send via cluster.command (TUYA_SET_DATA = 0x00)
            result = await cluster.command(0x00, cmd, expect_reply=True)
            _LOGGER.info(
                "Sent DP%d='%s' via TuyaCommand: %s",
                self._dp, value, result,
            )
        except Exception as exc:
            _LOGGER.error(
                "Failed to send DP%d='%s': %s",
                self._dp, value, exc,
            )
