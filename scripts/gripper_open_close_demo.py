#!/usr/bin/env python3
"""Demonstrate gripper full-open/full-close cycles without moving J1-J6."""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gripper_api import GripperController  # noqa: E402
from pose_bookmark import DEFAULT_SDK_ROOT, create_high_level_robot, read_feedback  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--open-rad", type=float, default=1.6,
                        help="official common open target; verify actual mechanical limit first")
    parser.add_argument("--open-vel", type=float, default=0.25)
    parser.add_argument("--close-vel", type=float, default=0.50)
    parser.add_argument("--max-tqu", type=float, default=0.50,
                        help="gripper torque limit; close only briefly against an empty stop")
    parser.add_argument("--sleep-duration", type=float, default=4.0,
                        help="seconds used to return J1-J6 to the all-zero sleep pose")
    parser.add_argument("--dwell", type=float, default=4.0,
                        help="hold each endpoint long enough for the full gripper travel")
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    args = parser.parse_args()

    if args.cycles < 1:
        parser.error("--cycles must be positive")
    if not 0.0 < args.open_rad <= 2.0:
        parser.error("--open-rad must be within the documented 0..2 rad command range")

    before = read_feedback(args.sdk_root)
    print(f"Before: gripper={before['gripper_rad']:.4f} rad ({math.degrees(before['gripper_rad']):.1f} deg)")
    robot = create_high_level_robot(args.sdk_root)
    try:
        print("Step 1: returning J1-J6 and gripper to sleep (all zero)")
        ok = robot.moveJ([0.0] * 6, duration=args.sleep_duration, iswait=False)
        if ok is False:
            raise RuntimeError("moveJ rejected sleep pose")
        time.sleep(max(args.sleep_duration, 0.2))
        robot.gripper_control(0.0, args.close_vel, args.max_tqu)
        time.sleep(args.dwell)
        gripper = GripperController(
            robot,
            open_rad=args.open_rad,
            close_rad=0.0,
            open_vel=args.open_vel,
            close_vel=args.close_vel,
            max_tqu=args.max_tqu,
            dwell=args.dwell,
        )
        for index in range(args.cycles):
            print(f"Cycle {index + 1}/{args.cycles}: 全开 {args.open_rad:.3f} rad -> 全关 0.000 rad")
            gripper.open()
            gripper.close()
        # Release the high-level serial object before returning; two SDK Robot
        # instances cannot share the port. A separate check_connection call
        # can be used after this process exits for readback.
        stop = getattr(robot, "set_stop", None)
        if callable(stop):
            stop()
        robot = None
        print("Gripper open/close demo complete; J1-J6 were first returned to sleep.")
    except KeyboardInterrupt:
        print("Interrupted; requesting stop.")
        raise
    finally:
        stop = getattr(robot, "set_stop", None)
        if callable(stop):
            stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
