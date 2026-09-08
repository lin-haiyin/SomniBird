#!/usr/bin/env python3
"""Read-only hand-teaching capture for a named six-joint + gripper pose."""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pose_bookmark import (  # noqa: E402
    DEFAULT_POSES,
    DEFAULT_SDK_ROOT,
    load_document,
    read_feedback,
    save_yaml_pose,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="pose name to save, e.g. blanket_pickup")
    parser.add_argument("--seconds", type=float, default=10.0,
                        help="capture window; use Ctrl+C to finish early")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--poses", type=Path, default=DEFAULT_POSES)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval <= 0:
        parser.error("seconds and interval must be positive")

    print("Read-only capture: no motion command will be sent.")
    print("手动摆好姿态后保持不动；时间到或按 Ctrl+C 将保存最后一次反馈。")
    latest = None
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            latest = read_feedback(args.sdk_root)
            joints = ", ".join(f"{math.degrees(v):.1f}°" for v in latest["joints_rad"])
            grip = math.degrees(latest["gripper_rad"])
            print(f"J1..J6=[{joints}], gripper={grip:.1f}°", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nCapture interrupted by operator; saving latest valid feedback.")

    if latest is None:
        raise RuntimeError("No valid feedback captured")
    document = load_document(args.poses)
    save_yaml_pose(args.poses, args.name, latest)
    print(f"Saved pose '{args.name}' to {args.poses}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
