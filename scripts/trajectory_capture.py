#!/usr/bin/env python3
"""Record a manually demonstrated arm motion as a timestamped JSONL trajectory."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pose_bookmark import DEFAULT_SDK_ROOT, sdk_paths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="trajectory name, e.g. blanket_scene1")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="maximum duration; 0 means record until Ctrl+C")
    parser.add_argument("--interval", type=float, default=0.05,
                        help="sampling interval in seconds (default 20 Hz)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "records" / "trajectories")
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    args = parser.parse_args()
    if args.seconds < 0 or args.interval <= 0:
        parser.error("seconds must be >= 0 and interval must be positive")

    sdk_paths(args.sdk_root)
    import hightorque_robot  # imported after SDK path setup

    config = args.sdk_root / "robot_param" / "Follower.yaml"
    robot = hightorque_robot.Robot(str(config))
    motors = robot.get_motors()
    if len(motors) != 7:
        raise RuntimeError(f"Expected 7 motors, received {len(motors)}")
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = args.output / f"trajectory_{stamp}_{args.name}.jsonl"
    print(f"Recording read-only feedback to {path}")
    print("请在允许手动示教的状态下摆动作；按 Ctrl+C 停止并保存。")

    count = 0
    start = time.monotonic()
    next_sample = start
    try:
        with path.open("w", encoding="utf-8") as handle:
            while args.seconds == 0 or time.monotonic() - start < args.seconds:
                now = time.monotonic()
                if now < next_sample:
                    time.sleep(next_sample - now)
                robot.send_get_motor_state_cmd()
                robot.motor_send_cmd()
                time.sleep(0.01)
                states = {motor.get_motor_id(): motor.get_current_motor_state() for motor in motors}
                if set(states) != set(range(1, 8)):
                    raise RuntimeError(f"Unexpected motor IDs: {sorted(states)}")
                sample = {
                    "t": round(time.monotonic() - start, 4),
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "motors": [
                        {
                            "id": motor_id,
                            "position_rad": float(states[motor_id].position),
                            "velocity_rad_s": float(states[motor_id].velocity),
                            "torque_nm": float(states[motor_id].torque),
                            "fault": int(states[motor_id].fault),
                        }
                        for motor_id in range(1, 8)
                    ],
                }
                if any(item["position_rad"] == 999.0 or item["fault"] != 0 for item in sample["motors"]):
                    raise RuntimeError("Invalid feedback or non-zero fault during recording")
                handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                handle.flush()
                count += 1
                next_sample += args.interval
    except KeyboardInterrupt:
        print("\nRecording stopped by operator.")
    finally:
        stop = getattr(robot, "motor_brake", None)
        if callable(stop):
            stop()
    if count == 0:
        path.unlink(missing_ok=True)
        raise RuntimeError("No samples captured; trajectory file was removed")
    print(f"Saved {count} samples to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
