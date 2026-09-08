#!/usr/bin/env python3
"""Repeatable playful nod action for Panthera-HT.

Sequence: sleep -> body pose (J2=50 deg, J3=45 deg) -> J4 nod cycles -> sleep.
All angles are degrees at the CLI and converted to radians for the SDK.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pose_bookmark import (  # noqa: E402
    DEFAULT_SDK_ROOT,
    create_high_level_robot,
    read_feedback,
    snapshot,
)


def deg(value: float) -> float:
    return math.radians(value)


def move_j(robot, joints_deg: list[float], duration: float) -> None:
    joints = [deg(value) for value in joints_deg]
    ok = robot.moveJ(joints, duration=duration, iswait=False)
    if ok is False:
        raise RuntimeError(f"moveJ rejected target: {joints_deg}")
    # Keep the command active for the requested interval. The vendor helper's
    # iswait=True path can return immediately within its default tolerance.
    time.sleep(max(duration, 0.2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--amplitude-deg", type=float, default=25.0)
    parser.add_argument("--body-duration", type=float, default=3.0)
    parser.add_argument("--nod-duration", type=float, default=1.2)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "records")
    args = parser.parse_args()

    if args.cycles < 1 or args.amplitude_deg <= 0 or args.body_duration <= 0 or args.nod_duration <= 0:
        parser.error("cycles and motion durations must be positive; amplitude must be > 0")
    if args.amplitude_deg > 80:
        parser.error("amplitude-deg must stay within the official J4 range")

    before = read_feedback(args.sdk_root)
    record = snapshot(args.records, "before_nod_action", before)
    print(f"Saved pre-action snapshot: {record}")

    robot = create_high_level_robot(args.sdk_root)
    sleep_pose = [0.0] * 6
    body_pose = [0.0, 50.0, 45.0, 0.0, 0.0, 0.0]
    nod_up = [0.0, 50.0, 45.0, args.amplitude_deg, 0.0, 0.0]
    nod_down = [0.0, 50.0, 45.0, -args.amplitude_deg, 0.0, 0.0]

    try:
        print("[1/4] Moving to sleep (all zero)")
        move_j(robot, sleep_pose, args.body_duration)
        robot.gripper_control(0.0, 0.12, 0.15)
        time.sleep(args.settle)

        print("[2/4] Raising body: J2=50 deg, J3=45 deg")
        move_j(robot, body_pose, args.body_duration)
        time.sleep(args.settle)

        print(f"[3/4] Nodding with J4 +/-{args.amplitude_deg:.1f} deg for {args.cycles} cycles")
        for index in range(args.cycles):
            move_j(robot, nod_up, args.nod_duration)
            move_j(robot, nod_down, args.nod_duration)
            print(f"  cycle {index + 1}/{args.cycles}")
        move_j(robot, body_pose, args.nod_duration)
        time.sleep(args.settle)

        print("[4/4] Returning to sleep")
        move_j(robot, sleep_pose, args.body_duration)
        robot.gripper_control(0.0, 0.12, 0.15)
        time.sleep(args.settle)
        print("Nod action complete")
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
