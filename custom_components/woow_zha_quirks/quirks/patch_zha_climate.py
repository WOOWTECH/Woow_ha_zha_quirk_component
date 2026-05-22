"""Patch ZHA climate platform to support extended fan modes and fix bugs.

This script patches three files in the ZHA library:
1. cluster_handlers/__init__.py - Fix write_attributes_safe attrid=None crash
2. climate/__init__.py - Extended fan_modes and set_fan_mode support
3. climate/const.py - Add SEQ_OF_OPERATION entry for full HVAC modes

Run inside the HA container:
  python3 /config/custom_zha_quirks/patch_zha_climate.py
"""

import os
import sys
import re

ZHA_BASE = "/usr/local/lib/python3.14/site-packages/zha"

# ─────────────────────────────────────────────────────────────────
# Patch 1: Fix write_attributes_safe attrid=None crash
# ─────────────────────────────────────────────────────────────────

def patch_write_attributes_safe():
    path = os.path.join(ZHA_BASE, "zigbee/cluster_handlers/__init__.py")
    with open(path) as f:
        content = f.read()

    # Remove any previous debug patches
    content = re.sub(
        r'        import logging as _dbg_log\n.*?write_attrs_safe.*?\n',
        '',
        content,
    )
    content = re.sub(
        r'            _dbg_log\.getLogger.*?write_attrs_safe.*?\n',
        '',
        content,
    )

    old = '''        res = await self.write_attributes(attributes, manufacturer=manufacturer)
        for record in res[0]:
            if record.status != Status.SUCCESS:
                try:
                    name = self.cluster.attributes[record.attrid].name
                    value = attributes.get(name, "unknown")
                except KeyError:
                    name = f"0x{record.attrid:04x}"
                    value = "unknown"

                raise ZHAException(
                    f"Failed to write attribute {name}={value}: {record.status}",
                )'''

    new = '''        res = await self.write_attributes(attributes, manufacturer=manufacturer)
        for record in res[0]:
            if record.status != Status.SUCCESS:
                if record.attrid is not None:
                    try:
                        name = self.cluster.attributes[record.attrid].name
                        value = attributes.get(name, "unknown")
                    except KeyError:
                        name = f"0x{record.attrid:04x}"
                        value = "unknown"
                else:
                    name = "unknown"
                    value = "unknown"

                raise ZHAException(
                    f"Failed to write attribute {name}={value}: {record.status}",
                )'''

    if old in content:
        content = content.replace(old, new)
        with open(path, 'w') as f:
            f.write(content)
        print(f"[OK] Patched write_attributes_safe in {path}")
        return True
    elif "record.attrid is not None" in content:
        print(f"[SKIP] write_attributes_safe already patched in {path}")
        return True
    else:
        print(f"[FAIL] Could not find pattern in {path}")
        # Try to find and show what's there
        for i, line in enumerate(content.split('\n')):
            if 'write_attributes_safe' in line:
                print(f"  Line {i+1}: {line.rstrip()}")
        return False


# ─────────────────────────────────────────────────────────────────
# Patch 2: Fix climate fan_modes and async_set_fan_mode
# ─────────────────────────────────────────────────────────────────

def patch_climate_fan():
    path = os.path.join(ZHA_BASE, "application/platforms/climate/__init__.py")
    with open(path) as f:
        content = f.read()

    # 2a. Add imports if needed
    if "FAN_LOW" not in content.split('\n')[0:50].__repr__():
        # Check actual imports
        old_import = '''    FAN_AUTO,
    FAN_ON,'''
        new_import = '''    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_ON,'''
        if old_import in content:
            content = content.replace(old_import, new_import, 1)
            print("[OK] Added FAN_LOW/MEDIUM/HIGH imports")
        elif "FAN_LOW," in content:
            print("[SKIP] Fan imports already present")
        else:
            print("[WARN] Could not add fan imports - check manually")

    # 2b. Add FAN_MODE_SEQUENCE mapping and name-to-FanMode mapping
    # Insert after existing imports block
    fan_mapping_code = '''
# Fan mode sequence to available modes mapping
_SEQ_TO_FAN_MODES = {
    0x00: [FAN_LOW, FAN_MEDIUM, FAN_HIGH],           # Low_Med_High
    0x01: [FAN_LOW, FAN_HIGH],                         # Low_High
    0x02: [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO],  # Low_Med_High_Auto
    0x03: [FAN_LOW, FAN_HIGH, FAN_AUTO],               # Low_High_Auto
    0x04: [FAN_ON, FAN_AUTO],                          # On_Auto
}

# Fan mode name to FanMode enum mapping
_FAN_NAME_TO_MODE = {
    FAN_AUTO: FanMode.Auto,
    FAN_ON: FanMode.On,
    FAN_LOW: FanMode.Low,
    FAN_MEDIUM: FanMode.Medium,
    FAN_HIGH: FanMode.High,
}

# FanMode enum to fan mode name
_FAN_MODE_TO_NAME = {v: k for k, v in _FAN_NAME_TO_MODE.items()}
'''

    if "_SEQ_TO_FAN_MODES" not in content:
        # Find a good insertion point: after the last top-level import
        # Look for the class definition
        class_pos = content.find("\nclass Thermostat")
        if class_pos == -1:
            class_pos = content.find("\nclass ")
        if class_pos > 0:
            content = content[:class_pos] + fan_mapping_code + content[class_pos:]
            print("[OK] Added fan mode mapping code")
        else:
            print("[FAIL] Could not find insertion point for fan mapping")
            return False
    else:
        print("[SKIP] Fan mode mapping already present")

    # 2c. Patch fan_mode property (returns current mode as string)
    old_fan_mode_prop = '''    @functools.cached_property
    def fan_mode(self) -> str | None:
        """Return current FAN mode."""
        if self._fan_cluster_handler is None:
            return None

        if (
            self._fan_cluster_handler.fan_mode is None
            or self._fan_cluster_handler.fan_mode > FanMode.Auto
        ):
            return FAN_AUTO

        if self._fan_cluster_handler.fan_mode >= FanMode.On:
            return FAN_ON
        return FAN_AUTO'''

    new_fan_mode_prop = '''    @functools.cached_property
    def fan_mode(self) -> str | None:
        """Return current FAN mode."""
        if self._fan_cluster_handler is None:
            return None

        mode = self._fan_cluster_handler.fan_mode
        if mode is None:
            return FAN_AUTO

        return _FAN_MODE_TO_NAME.get(FanMode(mode), FAN_AUTO)'''

    if old_fan_mode_prop in content:
        content = content.replace(old_fan_mode_prop, new_fan_mode_prop)
        print("[OK] Patched fan_mode property")
    elif "_FAN_MODE_TO_NAME.get" in content:
        print("[SKIP] fan_mode property already patched")
    else:
        print("[WARN] Could not patch fan_mode property - pattern not found")

    # 2d. Patch fan_modes property (returns list of available modes)
    old_fan_modes = '''    @functools.cached_property
    def fan_modes(self) -> list[str] | None:
        """Return supported FAN modes."""
        if not self._fan_cluster_handler:
            return None
        return [FAN_AUTO, FAN_ON]'''

    new_fan_modes = '''    @functools.cached_property
    def fan_modes(self) -> list[str] | None:
        """Return supported FAN modes."""
        if not self._fan_cluster_handler:
            return None
        seq = self._fan_cluster_handler.fan_mode_sequence
        if seq is not None and seq in _SEQ_TO_FAN_MODES:
            return _SEQ_TO_FAN_MODES[seq]
        return [FAN_AUTO, FAN_ON]'''

    if old_fan_modes in content:
        content = content.replace(old_fan_modes, new_fan_modes)
        print("[OK] Patched fan_modes property")
    elif "_SEQ_TO_FAN_MODES" in content and "fan_mode_sequence" in content:
        print("[SKIP] fan_modes already patched")
    else:
        print("[WARN] Could not patch fan_modes - pattern not found")

    # 2e. Patch async_set_fan_mode to support all modes
    old_set_fan = '''    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        if self._fan_cluster_handler is None:
            self.warning("Fan cluster handler is not available")
            return

        if not self.fan_modes or fan_mode not in self.fan_modes:
            self.warning("Unsupported '%s' fan mode", fan_mode)
            return

        mode = FanMode.On if fan_mode == FAN_ON else FanMode.Auto

        await self._fan_cluster_handler.async_set_speed(mode)'''

    new_set_fan = '''    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        if self._fan_cluster_handler is None:
            self.warning("Fan cluster handler is not available")
            return

        if not self.fan_modes or fan_mode not in self.fan_modes:
            self.warning("Unsupported '%s' fan mode", fan_mode)
            return

        mode = _FAN_NAME_TO_MODE.get(fan_mode, FanMode.Auto)
        await self._fan_cluster_handler.async_set_speed(mode)'''

    if old_set_fan in content:
        content = content.replace(old_set_fan, new_set_fan)
        print("[OK] Patched async_set_fan_mode")
    elif "_FAN_NAME_TO_MODE.get" in content:
        print("[SKIP] async_set_fan_mode already patched")
    else:
        print("[WARN] Could not patch async_set_fan_mode - pattern not found")

    with open(path, 'w') as f:
        f.write(content)
    print(f"[OK] Saved {path}")
    return True


# ─────────────────────────────────────────────────────────────────
# Patch 3: Add custom SEQ_OF_OPERATION for all HVAC modes
# ─────────────────────────────────────────────────────────────────

def patch_climate_const():
    """Add extra entries to SEQ_OF_OPERATION for devices supporting
    Cool+Heat+Dry+Fan_only (like VRV controllers).

    The default Cooling_and_Heating only maps to [OFF, HEAT_COOL, COOL, HEAT].
    We can't change the enum value, but we can add a custom entry or override
    at the quirk level.

    Actually, the best approach is to have the quirk set the system_mode
    values directly (Cool, Heat, Dry, Fan_only, Off), and override
    the hvac_modes by making the thermostat cluster handler report the
    correct sequence. The SEQ_OF_OPERATION constant maps
    ControlSequenceOfOperation → hvac modes.

    Since our device uses Cooling_and_Heating (0x04), we need to add
    Dry and Fan_only to that mapping entry.
    """
    path = os.path.join(ZHA_BASE, "application/platforms/climate/const.py")
    with open(path) as f:
        content = f.read()

    # Add Dry and Fan_only to the Cooling_and_Heating entries
    old_cooling_heating = '''    ControlSequenceOfOperation.Cooling_and_Heating: [
        HVACMode.OFF,
        HVACMode.HEAT_COOL,
        HVACMode.COOL,
        HVACMode.HEAT,
    ],
    ControlSequenceOfOperation.Cooling_and_Heating_with_Reheat: [
        HVACMode.OFF,
        HVACMode.HEAT_COOL,
        HVACMode.COOL,
        HVACMode.HEAT,
    ],'''

    new_cooling_heating = '''    ControlSequenceOfOperation.Cooling_and_Heating: [
        HVACMode.OFF,
        HVACMode.HEAT_COOL,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ],
    ControlSequenceOfOperation.Cooling_and_Heating_with_Reheat: [
        HVACMode.OFF,
        HVACMode.HEAT_COOL,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ],'''

    if old_cooling_heating in content:
        content = content.replace(old_cooling_heating, new_cooling_heating)
        with open(path, 'w') as f:
            f.write(content)
        print(f"[OK] Added DRY/FAN_ONLY to SEQ_OF_OPERATION in {path}")
        return True
    elif "HVACMode.DRY," in content and "HVACMode.FAN_ONLY," in content:
        print(f"[SKIP] SEQ_OF_OPERATION already has DRY/FAN_ONLY in {path}")
        return True
    else:
        print(f"[FAIL] Could not find SEQ_OF_OPERATION pattern in {path}")
        return False


# ─────────────────────────────────────────────────────────────────
# Clear __pycache__ for changed files
# ─────────────────────────────────────────────────────────────────

def clear_pycache():
    dirs = [
        os.path.join(ZHA_BASE, "zigbee/cluster_handlers/__pycache__"),
        os.path.join(ZHA_BASE, "application/platforms/climate/__pycache__"),
    ]
    count = 0
    for d in dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith('.pyc'):
                    os.remove(os.path.join(d, f))
                    count += 1
    print(f"[OK] Cleared {count} .pyc files")


if __name__ == "__main__":
    print("=== Patching ZHA climate platform ===\n")
    ok1 = patch_write_attributes_safe()
    ok2 = patch_climate_fan()
    ok3 = patch_climate_const()
    clear_pycache()
    print("\n=== Done ===")
    if ok1 and ok2 and ok3:
        print("All patches applied successfully. Restart HA to take effect.")
    else:
        print("Some patches failed. Check output above.")
        sys.exit(1)
