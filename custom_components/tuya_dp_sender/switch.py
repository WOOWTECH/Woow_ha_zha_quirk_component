"""Custom switch entities for tuya_dp_sender.

1) Motor direction switches for Tuya covers (DP5) — existing.
2) All On/All Off switches for Simon i7 multi-gang switches — NEW.
   These send standard ZCL OnOff commands to every endpoint on the device.
"""
import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tuya_dp_sender"

# ======== COVER DEVICES (motor direction) ========
COVER_DEVICES = [
    {"ieee": "cc:86:ec:ff:fe:a1:ea:33", "name": "Tuya Cover", "default_on": True},
    {"ieee": "44:e2:f8:ff:fe:b7:34:33", "name": "Tuya Cover 2", "default_on": True},
]

# ======== SIMON i7 ALL-ON/ALL-OFF ========
SIMON_ALL_ONOFF = [
    {
        "ieee": "90:35:ea:ff:fe:76:90:7c",
        "name": "Simon i7 3-Gang",
        "endpoints": [1, 2, 3],
    },
    {
        "ieee": "94:de:b8:ff:fe:18:0f:d5",
        "name": "Simon i7 2-Gang",
        "endpoints": [1, 2],
    },
    {
        "ieee": "b4:e3:f9:ff:fe:3f:a4:62",
        "name": "Simon i7 4-Gang",
        "endpoints": [1, 2, 3, 4],
    },
]
# ==================================================


async def async_setup_platform(
    hass: HomeAssistant, config, async_add_entities, discovery_info=None
):
    if discovery_info is None:
        return
    entities = []
    for dev in COVER_DEVICES:
        entities.append(
            TuyaMotorDirectionSwitch(hass, dev["ieee"], dev["name"], dev["default_on"])
        )
    for dev in SIMON_ALL_ONOFF:
        entities.append(
            SimonAllOnOffSwitch(hass, dev["ieee"], dev["name"], dev["endpoints"])
        )
    async_add_entities(entities)


# ─── Helper: get zigpy device from IEEE ──────────────────────
async def _get_zigpy_device(hass, ieee_str):
    """Return the zigpy device object for the given IEEE address."""
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
        return None
    app = gateway.application_controller
    norm = ieee_str.lower().replace(":", "")
    for dev in app.devices.values():
        if str(dev.ieee).lower().replace(":", "") == norm:
            return dev
    return None


# ─── Simon i7 All On/Off Switch ──────────────────────────────
class SimonAllOnOffSwitch(SwitchEntity):
    """Switch that turns all gangs on/off via ZCL OnOff commands."""

    _attr_icon = "mdi:light-switch"
    _attr_has_entity_name = False

    def __init__(self, hass, ieee, device_name, endpoints):
        self.hass = hass
        self._ieee = ieee
        self._device_name = device_name
        self._endpoints = endpoints
        self._attr_name = f"{device_name} All On/Off"
        self._attr_unique_id = f"simon_all_onoff_{ieee.replace(':', '')}"
        self._is_on = False

    @property
    def is_on(self):
        return self._is_on

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        try:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={("zha", self._ieee)})
            if device is not None:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, device_id=device.id)
        except Exception as exc:
            _LOGGER.warning("Failed to link All On/Off to ZHA device: %s", exc)

    async def async_turn_on(self, **kwargs):
        await self._send_all(True)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._send_all(False)
        self._is_on = False
        self.async_write_ha_state()

    async def _send_all(self, turn_on: bool):
        """Send ZCL OnOff on/off command to every endpoint."""
        device = await _get_zigpy_device(self.hass, self._ieee)
        if device is None:
            _LOGGER.error("Device %s not found for All On/Off", self._ieee)
            return
        cmd_id = 0x01 if turn_on else 0x00  # on=1, off=0
        action = "on" if turn_on else "off"
        for ep_id in self._endpoints:
            ep = device.endpoints.get(ep_id)
            if ep is None:
                _LOGGER.warning("Endpoint %d not found on %s", ep_id, self._ieee)
                continue
            cluster = ep.in_clusters.get(0x0006)  # OnOff cluster
            if cluster is None:
                _LOGGER.warning("OnOff cluster not found on EP%d of %s", ep_id, self._ieee)
                continue
            try:
                await cluster.command(cmd_id)
                _LOGGER.info("All %s: EP%d OK on %s", action, ep_id, self._ieee)
            except Exception as exc:
                _LOGGER.error("All %s: EP%d failed on %s: %s", action, ep_id, self._ieee, exc)


# ─── Motor Direction Switch (existing) ───────────────────────
class TuyaMotorDirectionSwitch(SwitchEntity):
    """Switch to control Tuya cover motor direction (DP5)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:swap-horizontal"
    _attr_has_entity_name = False

    def __init__(self, hass, ieee, device_name, default_on):
        self.hass = hass
        self._ieee = ieee
        self._device_name = device_name
        self._default_on = default_on
        self._attr_name = f"{device_name} Motor Direction"
        self._attr_unique_id = f"tuya_motor_dir_{ieee.replace(':', '')}"
        self._is_on = default_on

    @property
    def is_on(self):
        return self._is_on

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        try:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={("zha", self._ieee)})
            if device is not None:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, device_id=device.id)
        except Exception as exc:
            _LOGGER.warning("Failed to link to ZHA device: %s", exc)

        self._is_on = self._default_on

        async def _apply_on_startup(event):
            await asyncio.sleep(35)
            value = 1 if self._is_on else 0
            _LOGGER.warning(
                "Startup: applying DP5=%d to %s (%s)",
                value, self._device_name, self._ieee,
            )
            try:
                await self._send_dp5(value)
            except Exception as exc:
                _LOGGER.error("Failed to apply DP5 to %s: %s", self._ieee, exc)

        self.hass.bus.async_listen_once("homeassistant_started", _apply_on_startup)

    async def async_turn_on(self, **kwargs):
        await self._send_dp5(1)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._send_dp5(0)
        self._is_on = False
        self.async_write_ha_state()

    async def _send_dp5(self, value):
        data = self.hass.data.get(DOMAIN)
        if data is None:
            return
        handle = data.get("handle_send_dp")
        if handle is None:
            return
        await handle(
            type("FakeCall", (), {"data": {
                "ieee": self._ieee, "dp": 5, "dp_type": 4, "value": value,
            }})()
        )
