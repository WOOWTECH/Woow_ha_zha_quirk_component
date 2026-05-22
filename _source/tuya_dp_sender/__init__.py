"""Tuya DP Sender - send raw Tuya DP commands directly via ZHA/zigpy."""
import asyncio
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tuya_dp_sender"


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Tuya DP Sender integration."""

    async def _get_cluster(ieee_str):
        """Get the Tuya MCU cluster for a device by IEEE address."""
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
            _LOGGER.error("ZHA gateway not found (zha type=%s)", type(zha))
            return None, None

        app = gateway.application_controller
        norm = ieee_str.lower().replace(":", "")
        device = None
        for dev in app.devices.values():
            if str(dev.ieee).lower().replace(":", "") == norm:
                device = dev
                break

        if device is None:
            _LOGGER.error("Device %s not found", ieee_str)
            return None, None

        ep = device.endpoints.get(1)
        if ep is None:
            _LOGGER.error("Endpoint 1 not found on %s", ieee_str)
            return None, None

        cluster = ep.in_clusters.get(0xEF00)
        if cluster is None:
            _LOGGER.error("Tuya cluster 0xEF00 not found on %s", ieee_str)
            return None, None

        return cluster, app

    async def _send_tuya_command_new(cluster, app, dp, dp_type, value):
        """Send DP via TuyaCommand schema (for TuyaMCUCluster-based clusters)."""
        from zhaquirks.tuya import TuyaCommand, TuyaDatapointData, TuyaData
        import zigpy.types as t

        # Construct the correct data value based on dp_type
        if dp_type == 1:  # BOOL
            data_val = TuyaData(t.Bool(bool(value)))
        elif dp_type == 2:  # VALUE (uint32)
            data_val = TuyaData(t.uint32_t(int(value)))
        elif dp_type == 4:  # ENUM
            data_val = TuyaData(t.enum8(int(value)))
        elif dp_type == 3:  # STRING
            data_val = TuyaData(str(value))
        else:
            data_val = TuyaData(t.uint32_t(int(value)))

        dpd = TuyaDatapointData(dp=dp, data=data_val)
        tsn = app.get_sequence()

        cmd_payload = TuyaCommand(
            status=0,
            tsn=tsn,
            datapoints=[dpd],
        )

        _LOGGER.info(
            "Sending TuyaCommand: dp=%d type=%d value=%s tsn=%d",
            dp, dp_type, value, tsn,
        )

        result = await cluster.command(0x00, cmd_payload, expect_reply=False)
        _LOGGER.info("TuyaCommand result: %s", result)
        return True

    async def _send_tuya_command_old(cluster, cmd_id, payload):
        """Send via old Command schema (for TuyaReplacementCluster devices)."""
        _LOGGER.info("SET_DATA cmd_id=0x%04X payload=%s", cmd_id, payload)

        for attempt in ("command_with_param", "command_positional"):
            try:
                from zhaquirks.tuya import Command
                cmd_obj = Command()
                cmd_obj.status = 0
                cmd_obj.tsn = 0
                cmd_obj.command_id = cmd_id
                cmd_obj.function = 0
                cmd_obj.data = payload

                if attempt == "command_with_param":
                    result = await cluster.command(0x00, param=cmd_obj)
                else:
                    result = await cluster.command(0x00, cmd_obj)
                _LOGGER.info("Success via '%s': %s", attempt, result)
                return True
            except Exception as exc:
                _LOGGER.warning("Attempt '%s' failed: %s", attempt, exc)
        return False

    async def _send_raw_frame(cluster, app, dp, dp_type, value):
        """Send raw ZCL frame bypassing all schema (last resort)."""
        # Build Tuya set_data payload manually:
        # status(1) + tsn(1) + dp(1) + dp_type(1) + data_len(2 BE) + data(N)
        tsn = app.get_sequence() & 0xFF

        if dp_type == 1:  # BOOL
            data_bytes = bytes([1 if value else 0])
        elif dp_type == 2:  # VALUE (uint32 BE)
            v = int(value)
            data_bytes = v.to_bytes(4, "big")
        elif dp_type == 4:  # ENUM
            data_bytes = bytes([int(value) & 0xFF])
        else:
            data_bytes = bytes([int(value) & 0xFF])

        data_len = len(data_bytes)
        tuya_payload = bytes([0x00, tsn, dp, dp_type,
                             (data_len >> 8) & 0xFF, data_len & 0xFF]) + data_bytes

        # Build ZCL frame: frame_ctrl(1) + seq(1) + cmd_id(1) + payload
        seq = app.get_sequence() & 0xFF
        zcl_frame = bytes([0x11, seq, 0x00]) + tuya_payload  # cmd 0x00 = set_data

        _LOGGER.info(
            "Sending RAW frame: dp=%d type=%d value=%s frame=%s",
            dp, dp_type, value, zcl_frame.hex(),
        )

        device = cluster.endpoint.device
        result = await device.request(
            profile=260,
            cluster=0xEF00,
            src_ep=1,
            dst_ep=1,
            sequence=seq,
            data=zcl_frame,
            expect_reply=False,
        )
        _LOGGER.info("RAW frame result: %s", result)
        return True

    async def handle_send_dp(call: ServiceCall):
        """Handle send_dp service call (BOOL/VALUE/ENUM)."""
        ieee_str = call.data["ieee"]
        dp = call.data["dp"]
        dp_type = call.data.get("dp_type", 4)
        value = call.data["value"]

        _LOGGER.info(
            "tuya_dp_sender: sending DP%d=%d (type=%d) to %s",
            dp, value, dp_type, ieee_str,
        )

        cluster, app = await _get_cluster(ieee_str)
        if cluster is None:
            return

        # Try method 1: TuyaCommand schema (for TuyaMCUCluster)
        try:
            ok = await _send_tuya_command_new(cluster, app, dp, dp_type, value)
            if ok:
                return
        except Exception as exc:
            _LOGGER.warning("TuyaCommand method failed: %s", exc)

        # Try method 2: Old Command schema (for TuyaReplacementCluster)
        cmd_id = (dp_type << 8) | dp
        if dp_type == 4:
            payload = [1, value & 0xFF]
        elif dp_type == 2:
            payload = [4, (value >> 24) & 0xFF, (value >> 16) & 0xFF,
                       (value >> 8) & 0xFF, value & 0xFF]
        elif dp_type == 1:
            payload = [1, 1 if value else 0]
        else:
            payload = [1, value & 0xFF]

        try:
            ok = await _send_tuya_command_old(cluster, cmd_id, payload)
            if ok:
                return
        except Exception as exc:
            _LOGGER.warning("Old Command method failed: %s", exc)

        # Try method 3: Raw frame (bypasses all schema)
        try:
            ok = await _send_raw_frame(cluster, app, dp, dp_type, value)
            if ok:
                return
        except Exception as exc:
            _LOGGER.warning("Raw frame method failed: %s", exc)

        _LOGGER.error("All attempts to send DP%d=%d failed", dp, value)

    async def handle_send_dp_string(call: ServiceCall):
        """Handle send_dp_string service call (STRING type=3)."""
        ieee_str = call.data["ieee"]
        dp = call.data["dp"]
        text = call.data["value"]

        _LOGGER.info(
            "tuya_dp_sender: sending STRING DP%d='%s' to %s",
            dp, text, ieee_str,
        )

        cluster, app = await _get_cluster(ieee_str)
        if cluster is None:
            return

        # Try TuyaCommand method first
        try:
            ok = await _send_tuya_command_new(cluster, app, dp, 3, text)
            if ok:
                return
        except Exception as exc:
            _LOGGER.warning("TuyaCommand string method failed: %s", exc)

        # Try old method
        dp_type = 3
        cmd_id = (dp_type << 8) | dp
        encoded = text.encode("utf-8")
        payload = [len(encoded)] + list(encoded)

        try:
            ok = await _send_tuya_command_old(cluster, cmd_id, payload)
            if ok:
                return
        except Exception as exc:
            _LOGGER.warning("Old string method failed: %s", exc)

        _LOGGER.error("All attempts to send STRING DP%d='%s' failed", dp, text)

    hass.services.async_register(
        DOMAIN, "send_dp", handle_send_dp,
        schema=vol.Schema({
            vol.Required("ieee"): str,
            vol.Required("dp"): vol.Coerce(int),
            vol.Optional("dp_type", default=4): vol.Coerce(int),
            vol.Required("value"): vol.Coerce(int),
        }),
    )

    hass.services.async_register(
        DOMAIN, "send_dp_string", handle_send_dp_string,
        schema=vol.Schema({
            vol.Required("ieee"): str,
            vol.Required("dp"): vol.Coerce(int),
            vol.Required("value"): str,
        }),
    )
    _LOGGER.info("tuya_dp_sender: services registered (send_dp + send_dp_string)")

    hass.data[DOMAIN] = {
        "handle_send_dp": handle_send_dp,
        "handle_send_dp_string": handle_send_dp_string,
    }

    from homeassistant.helpers.discovery import async_load_platform
    hass.async_create_task(async_load_platform(hass, "switch", DOMAIN, {}, config))
    hass.async_create_task(async_load_platform(hass, "button", DOMAIN, {}, config))
    hass.async_create_task(async_load_platform(hass, "select", DOMAIN, {}, config))
    hass.async_create_task(async_load_platform(hass, "text", DOMAIN, {}, config))

    return True
