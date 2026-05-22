"""ZHA Quirk for Tuya TS0601 cover motor _TZE284_qxjkdfyt.

捲簾電機馬達 (roller shade motor) — TZE284 protocol (same DPs as TZE200).

DP map:
  DP1   - ENUM  - cover control: 0=open, 1=stop, 2=close
  DP2   - VALUE - set target position (0-100)
  DP3   - VALUE - current position report (0-100)
  DP5   - ENUM  - motor direction: 0=forward, 1=reversed
  DP7   - ENUM  - work state
  DP101 - BOOL  - remote register (pairing)
  DP102 - BOOL  - reset all limits
  DP103 - BOOL  - upper limit confirm/reset
  DP104 - BOOL  - middle limit confirm/reset
  DP105 - BOOL  - lower limit confirm/reset
  DP106 - ENUM  - motor mode: 0=linkage, 1=inching
"""

from zhaquirks.tuya.builder import TuyaQuirkBuilder

(
    TuyaQuirkBuilder("_TZE284_qxjkdfyt", "TS0601")
    .tuya_cover(
        control_dp=1,
        position_state_dp=3,
        position_control_dp=2,
        invert=True,
    )
    .skip_configuration()
    .add_to_registry()
)
