#!/usr/bin/env python3
"""Sleep-entertainment scene 2: intervene between a person and a phone."""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pose_bookmark import DEFAULT_SDK_ROOT, create_high_level_robot, read_feedback, snapshot  # noqa: E402


def move_j(robot, joints_deg: list[float], duration: float) -> None:
    target = [math.radians(value) for value in joints_deg]
    ok = robot.moveJ(target, duration=duration, iswait=False)
    if ok is False:
        raise RuntimeError(f"moveJ rejected target: {joints_deg}")
    time.sleep(max(duration, 0.2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gripper-open-deg", type=float, default=math.degrees(1.6))
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--sleep-duration", type=float, default=4.0)
    parser.add_argument("--pose-duration", type=float, default=4.0)
    parser.add_argument("--gripper-duration", type=float, default=1.5)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "records")
    args = parser.parse_args()

    if args.cycles < 1 or args.gripper_open_deg <= 0 or args.gripper_open_deg > math.degrees(2.0):
        parser.error("cycles must be positive and gripper-open-deg must be within the official 0..2 rad range")

    before = read_feedback(args.sdk_root)
    record = snapshot(args.records, "before_phone_intervention_scene2", before)
    print(f"Saved pre-action snapshot: {record}")

    robot = create_high_level_robot(args.sdk_root)
    sleep_pose = [0.0] * 6
    # Assumption: J6 positive is the requested counter-clockwise direction.
    scene_pose = [0.0, 100.0, 75.0, 15.0, 0.0, 90.0]
    try:
        print("[1/4] Returning to sleep")
        move_j(robot, sleep_pose, args.sleep_duration)
        robot.gripper_control(0.0, 0.12, 0.15)
        time.sleep(args.settle)

        print("[2/4] Scene pose: J2=100°, J3=75°, J4=15°, J6=+90°")
        move_j(robot, scene_pose, args.pose_duration)
        time.sleep(args.settle)

        print(f"[3/4] Gripper open/close for {args.cycles} cycles")
        for index in range(args.cycles):
            robot.gripper_control(math.radians(args.gripper_open_deg), 0.25, 0.5)
            time.sleep(args.gripper_duration)
            robot.gripper_control(0.0, 0.25, 0.5)
            time.sleep(args.gripper_duration)
            print(f"  cycle {index + 1}/{args.cycles}")

        print("[4/4] Returning to sleep")
        move_j(robot, sleep_pose, args.sleep_duration)
        robot.gripper_control(0.0, 0.12, 0.15)
        time.sleep(args.settle)
        print("Phone intervention scene 2 complete")
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
