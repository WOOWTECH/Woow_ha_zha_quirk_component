"""Tuya TS0601 curtain track quirk for _TZE200_nogaemzt.

開合簾 (curtain track) — DP2 for position, default control mapping.

DP map:
  DP1  - ENUM  - cover control: 0=open, 1=stop, 2=close
  DP2  - VALUE - position (0-100), set AND report
  DP5  - ENUM  - motor direction: 0=normal, 1=reversed (volatile!)
  DP7  - ENUM  - work state: 0=idle, 1=moving
"""

import logging
from zigpy.profiles import zha

from zhaquirks.const import (
    DEVICE_TYPE,
    ENDPOINTS,
    INPUT_CLUSTERS,
    MODELS_INFO,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
)
from zhaquirks.tuya import (
    TuyaManufacturerWindowCover,
    TuyaWindowCover,
    TuyaWindowCoverControl,
)

_LOGGER = logging.getLogger(__name__)


class TuyaCover_nogaemzt(TuyaWindowCover):
    """Tuya TS0601 curtain track _TZE200_nogaemzt."""

    # Default mapping: UPOPEN→0, DOWNCLOSE→2, STOP→1
    tuya_cover_command = {
        0x0000: 0x0000,  # UPOPEN  -> DP1=0 (open)
        0x0001: 0x0002,  # DOWNCLOSE -> DP1=2 (close)
        0x0002: 0x0001,  # STOP -> DP1=1
    }

    tuya_cover_inverted_by_default = True

    signature = {
        MODELS_INFO: [("_TZE200_nogaemzt", "TS0601")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: 0x0051,
                INPUT_CLUSTERS: [0x0000, 0x0004, 0x0005, 0x000a, 0xEF00],
                OUTPUT_CLUSTERS: [0x0019],
            }
        },
    }

    replacement = {
        ENDPOINTS: {
            1: {
                DEVICE_TYPE: zha.DeviceType.WINDOW_COVERING_DEVICE,
                INPUT_CLUSTERS: [
                    0x0000,
                    0x0004,
                    0x0005,
                    0x000a,
                    TuyaManufacturerWindowCover,
                    TuyaWindowCoverControl,
                ],
                OUTPUT_CLUSTERS: [
                    0x0019,
                ],
            }
        },
    }
