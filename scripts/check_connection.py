#!/usr/bin/env python3
"""Read Panthera-HT feedback without sending any motion target.

This uses the vendor's low-level SDK and the vendor Follower.yaml configuration.
It asks the CAN network for motor state only.  It never calls moveJ, moveL,
position, velocity, torque, or gripper control APIs.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import hightorque_robot as htr


DEFAULT_SDK_ROOT = Path(
    os.environ.get(
        "PANTHERA_SDK_ROOT",
        "~/高擎六轴机械臂开源资料/07_高擎官方资料/01_Panthera-HT_SDK/panthera_python",
    )
).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3, help="state request rounds")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be at least 1")

    config = DEFAULT_SDK_ROOT / "robot_param" / "Follower.yaml"
    if not config.is_file():
        raise FileNotFoundError(f"Official Follower.yaml was not found: {config}")

    robot = htr.Robot(str(config))
    motors = robot.get_motors()
    if len(motors) != 7:
        raise RuntimeError(f"Expected 7 motors, received {len(motors)}")

    for _ in range(args.samples):
        robot.send_get_motor_state_cmd()
        robot.motor_send_cmd()
        time.sleep(0.25)

    invalid = []
    print("id,position_rad,velocity_rad_s,torque_nm,mode,fault")
    for motor in motors:
        state = motor.get_current_motor_state()
        print(
            f"{motor.get_motor_id()},{state.position:.4f},{state.velocity:.4f},"
            f"{state.torque:.4f},{state.mode},0x{state.fault:02X}"
        )
        if state.position == 999.0 or state.fault != 0:
            invalid.append(motor.get_motor_id())

    if invalid:
        raise RuntimeError(f"No valid zero-fault feedback from motor IDs: {invalid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
