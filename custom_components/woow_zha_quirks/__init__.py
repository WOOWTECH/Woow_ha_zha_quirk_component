"""WOOW ZHA Quirks - 集中管理自訂 ZHA Quirks 與 Tuya 裝置支援。

安裝後在 configuration.yaml 加入 `woow_zha_quirks:` 即可自動載入所有 quirks，
不需要手動設定 zha.custom_quirks_path。
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pathlib
import pkgutil
import sys

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "woow_zha_quirks"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """設定 WOOW ZHA Quirks 元件，自動載入所有內建 quirks。"""

    quirks_path = pathlib.Path(__file__).parent / "quirks"

    _LOGGER.info("WOOW ZHA Quirks: 正在從 %s 載入自訂 quirks", quirks_path)

    loaded_count = 0

    def _load_quirks() -> int:
        """在 executor 中載入 quirk 模組（避免阻塞事件迴圈）。"""
        count = 0
        for importer, modname, _ispkg in pkgutil.walk_packages(
            path=[str(quirks_path)]
        ):
            # 跳過 __init__
            if modname == "__init__":
                continue

            full_modname = f"{DOMAIN}.quirks.{modname}"
            _LOGGER.debug("WOOW ZHA Quirks: 載入 quirk 模組 %s", full_modname)

            try:
                spec = importer.find_spec(modname)
                if spec is None:
                    _LOGGER.warning(
                        "WOOW ZHA Quirks: 找不到模組 spec: %s", modname
                    )
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[full_modname] = module
                spec.loader.exec_module(module)
                count += 1
            except Exception:
                _LOGGER.exception(
                    "WOOW ZHA Quirks: 載入 quirk 模組失敗: %s", modname
                )

        return count

    loaded_count = await hass.async_add_executor_job(_load_quirks)

    _LOGGER.info(
        "WOOW ZHA Quirks: 成功載入 %d 個 quirk 模組",
        loaded_count,
    )

    return True
