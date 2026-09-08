#!/usr/bin/env python3
"""Sleep scene 1: lift/spread a blanket, release it, then return to sleep."""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gripper_api import GripperController  # noqa: E402
from pose_bookmark import DEFAULT_SDK_ROOT, create_high_level_robot, read_feedback, snapshot  # noqa: E402


def move_j(robot, joints_deg: list[float], duration: float) -> None:
    target = [math.radians(value) for value in joints_deg]
    ok = robot.moveJ(target, duration=duration, iswait=False)
    if ok is False:
        raise RuntimeError(f"moveJ rejected target: {joints_deg}")
    time.sleep(max(duration, 0.2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gripper-open-rad", type=float, default=1.0)
    parser.add_argument("--gripper-close-rad", type=float, default=0.0)
    parser.add_argument("--open-seconds", type=float, default=3.0)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--move-duration", type=float, default=6.0)
    parser.add_argument("--open-vel", type=float, default=0.5)
    parser.add_argument("--close-vel", type=float, default=0.5)
    parser.add_argument("--max-tqu", type=float, default=0.5)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "records")
    args = parser.parse_args()

    if args.open_seconds < 0 or args.settle_seconds < 0 or args.move_duration <= 0:
        parser.error("time parameters are out of range")
    if not 0.0 <= args.gripper_close_rad <= args.gripper_open_rad <= 2.0:
        parser.error("gripper positions must satisfy 0 <= close <= open <= 2 rad")

    before = read_feedback(args.sdk_root)
    record = snapshot(args.records, "before_sleep_scene1_blanket", before)
    print(f"Saved pre-action snapshot: {record}")

    # The operator views the arm from its back: left/right are mapped to J1
    # negative/positive, and "based on current position" is a relative offset.
    # blanket01 uses the vertical-gripper rest pose. Keep the generic
    # arm_action default sleep unchanged for all other scenes.
    sleep_pose_rad = [0.0, 0.0, 0.0, 0.0, 0.0, -math.pi / 2.0]
    sleep_pose = [math.degrees(value) for value in sleep_pose_rad]
    pickup_pose = [-45.0, 135.0, 90.0, 30.0, 0.0, 0.0]
    lift_pose = [-35.0, 145.0, 90.0, 30.0, 0.0, 0.0]
    spread_pose = [100.0, 145.0, 90.0, 30.0, 0.0, 0.0]

    robot = create_high_level_robot(args.sdk_root)
    gripper = GripperController(
        robot,
        open_rad=args.gripper_open_rad,
        close_rad=args.gripper_close_rad,
        open_vel=args.open_vel,
        close_vel=args.close_vel,
        max_tqu=args.max_tqu,
        dwell=0.0,
    )
    try:
        print("[1/8] Return to sleep2: J1..J5=0°, J6=-90°, gripper=0")
        move_j(robot, sleep_pose, args.move_duration)
        gripper.close(dwell=0.8)

        print("[2/8] Move to blanket pose: J1=-45°(左), J2=135°(前), J3=90°(上), J4=30°(右)")
        move_j(robot, pickup_pose, args.move_duration)
        print(f"[3/8] Open gripper to {args.gripper_open_rad:.3f} rad for {args.open_seconds:.1f}s")
        gripper.open(dwell=args.open_seconds)
        print(f"[4/8] Close gripper to {args.gripper_close_rad:.3f} rad")
        gripper.close(dwell=0.8)

        print("[5/8] Lift J1/J2 by +10°: J1=-35°, J2=145°")
        move_j(robot, lift_pose, args.move_duration)
        print("[6/8] Move J1 right by 135° from -35° -> +100° and stabilize")
        move_j(robot, spread_pose, args.move_duration)
        time.sleep(args.settle_seconds)

        print(f"[7/8] Release blanket: open gripper to {args.gripper_open_rad:.3f} rad for {args.open_seconds:.1f}s")
        gripper.open(dwell=args.open_seconds)
        print("Blanket released; close gripper")
        gripper.close(dwell=0.8)

        print("[8/8] Return to sleep2")
        move_j(robot, sleep_pose, args.move_duration)
        gripper.close(dwell=0.8)
        print("Sleep scene 1 (blanket) complete")
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
