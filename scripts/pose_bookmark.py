#!/usr/bin/env python3
"""Read, save, preview, and explicitly execute named Panthera-HT poses.

The command is deliberately dry-run by default. It never changes motor zero
calibration. A pose is project-level memory, not an undo stack in the robot.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - gives an actionable CLI error
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSES = PROJECT_ROOT / "configs" / "poses.yaml"
DEFAULT_RECORDS = PROJECT_ROOT / "records"
DEFAULT_SDK_ROOT = Path(
    os.environ.get(
        "PANTHERA_SDK_ROOT",
        "~/高擎六轴机械臂开源资料/07_高擎官方资料/01_Panthera-HT_SDK/panthera_python",
    )
).expanduser()


def load_document(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    if not isinstance(document, dict) or not isinstance(document.get("poses"), dict):
        raise ValueError(f"Invalid pose document: {path}")
    return document


def get_pose(document: dict[str, Any], name: str) -> dict[str, Any]:
    pose = document["poses"].get(name)
    if not isinstance(pose, dict):
        available = ", ".join(sorted(document["poses"])) or "(none)"
        raise KeyError(f"Unknown pose {name!r}; available: {available}")
    joints = pose.get("joints_rad")
    gripper = pose.get("gripper_rad")
    if joints is None or gripper is None:
        raise ValueError(f"Pose {name!r} has not been captured yet")
    if not isinstance(joints, list) or len(joints) != 6:
        raise ValueError(f"Pose {name!r} must contain six joints_rad values")
    values = [float(value) for value in joints] + [float(gripper)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Pose {name!r} contains a non-finite value")
    return {"joints_rad": values[:6], "gripper_rad": values[6], "note": pose.get("note", "")}


def sdk_paths(sdk_root: Path) -> Path:
    scripts = sdk_root / "scripts"
    if not scripts.is_dir():
        raise FileNotFoundError(f"Official SDK scripts directory was not found: {scripts}")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return scripts


def read_feedback(sdk_root: Path) -> dict[str, Any]:
    """Read all seven motors using the vendor low-level state API only."""
    sdk_paths(sdk_root)
    htr = importlib.import_module("hightorque_robot")
    config = sdk_root / "robot_param" / "Follower.yaml"
    robot = htr.Robot(str(config))
    motors = robot.get_motors()
    if len(motors) != 7:
        raise RuntimeError(f"Expected 7 motors, received {len(motors)}")
    for _ in range(3):
        robot.send_get_motor_state_cmd()
        robot.motor_send_cmd()
        time.sleep(0.12)
    states = {motor.get_motor_id(): motor.get_current_motor_state() for motor in motors}
    invalid = [motor_id for motor_id, state in states.items() if state.position == 999.0 or state.fault != 0]
    if invalid:
        raise RuntimeError(f"Invalid or faulted motor feedback: {invalid}")
    ordered = [states[index] for index in range(1, 8)]
    return {
        "joints_rad": [float(state.position) for state in ordered[:6]],
        "gripper_rad": float(ordered[6].position),
        "motors": [
            {
                "id": index,
                "position_rad": float(state.position),
                "velocity_rad_s": float(state.velocity),
                "torque_nm": float(state.torque),
                "mode": str(state.mode),
                "fault": int(state.fault),
            }
            for index, state in enumerate(ordered, 1)
        ],
    }


def save_yaml_pose(path: Path, name: str, feedback: dict[str, Any]) -> None:
    document = load_document(path)
    if name not in document["poses"]:
        document["poses"][name] = {"note": "Captured from motor feedback"}
    document["poses"][name]["joints_rad"] = [round(value, 6) for value in feedback["joints_rad"]]
    # The closed-stop encoder can report a tiny negative offset (for example
    # -0.011 rad), but the vendor gripper command only accepts [0, 2] rad.
    # Normalize it when saving a named pose so future plant/replay commands do
    # not fail before the first motion sample.
    gripper = max(0.0, min(2.0, float(feedback["gripper_rad"])))
    document["poses"][name]["gripper_rad"] = round(gripper, 6)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(document, handle, allow_unicode=False, sort_keys=False)


def snapshot(records: Path, label: str, feedback: dict[str, Any]) -> Path:
    records.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = records / f"{stamp}_{label}.json"
    payload = {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "label": label, **feedback}
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def load_snapshot(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid snapshot: {path}")
    joints = payload.get("joints_rad")
    gripper = payload.get("gripper_rad")
    if not isinstance(joints, list) or len(joints) != 6 or gripper is None:
        raise ValueError(f"Snapshot must contain six joints_rad values and gripper_rad: {path}")
    values = [float(value) for value in joints] + [float(gripper)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Snapshot contains a non-finite value: {path}")
    return {"joints_rad": values[:6], "gripper_rad": values[6], "note": f"Snapshot: {path.name}"}


def create_high_level_robot(sdk_root: Path) -> Any:
    sdk_paths(sdk_root)
    module = importlib.import_module("Panthera_lib")
    cls = getattr(module, "Panthera")
    config = sdk_root / "robot_param" / "Follower.yaml"
    # SDK revisions have used both constructors; retain compatibility.
    for args in ((str(config),), tuple()):
        try:
            return cls(*args)
        except TypeError:
            continue
    raise RuntimeError("Could not construct Panthera_lib.Panthera with this SDK revision")


def print_pose(name: str, pose: dict[str, Any]) -> None:
    joints = ", ".join(f"{value:.6f}" for value in pose["joints_rad"])
    joints_deg = ", ".join(f"{math.degrees(value):.1f}" for value in pose["joints_rad"])
    print(f"{name}: joints_rad=[{joints}], gripper_rad={pose['gripper_rad']:.6f}")
    print(f"  joints_deg=[{joints_deg}], gripper_deg={math.degrees(pose['gripper_rad']):.1f}")
    if pose.get("note"):
        print(f"  note: {pose['note']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "show", "save-current", "move", "restore"))
    parser.add_argument("name", nargs="?", help="named pose")
    parser.add_argument("--poses", type=Path, default=DEFAULT_POSES)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--duration", type=float, default=8.0, help="moveJ duration in seconds")
    parser.add_argument("--execute", action="store_true", help="actually send the motion target")
    parser.add_argument("--allow-large", action="store_true", help="allow a joint delta over 0.8 rad")
    args = parser.parse_args()
    document = load_document(args.poses)

    if args.command == "list":
        for name, raw in document["poses"].items():
            ready = isinstance(raw, dict) and raw.get("joints_rad") is not None and raw.get("gripper_rad") is not None
            print(f"{name}: {'ready' if ready else 'empty'}")
        return 0
    if not args.name:
        parser.error("this command requires a pose name")

    if args.command == "show":
        print_pose(args.name, get_pose(document, args.name))
        return 0
    if args.command == "save-current":
        feedback = read_feedback(args.sdk_root)
        save_yaml_pose(args.poses, args.name, feedback)
        print_pose(args.name, {**feedback, "note": "Captured from motor feedback"})
        print(f"Saved current feedback to {args.poses}")
        return 0

    target = load_snapshot(Path(args.name)) if args.command == "restore" else get_pose(document, args.name)
    current = read_feedback(args.sdk_root)
    deltas = [abs(a - b) for a, b in zip(target["joints_rad"], current["joints_rad"])]
    max_delta = max(deltas)
    print_pose(args.name, target)
    print("Current joints_rad=[" + ", ".join(f"{x:.6f}" for x in current["joints_rad"]) + "]")
    print("Current joints_deg=[" + ", ".join(f"{math.degrees(x):.1f}" for x in current["joints_rad"]) + "]")
    print(f"Maximum joint delta: {max_delta:.6f} rad ({math.degrees(max_delta):.1f} deg)")
    if max_delta > 0.8 and not args.allow_large:
        raise RuntimeError("Motion refused: max joint delta exceeds 0.8 rad; review path and add --allow-large")
    if not args.execute:
        print("Preview only. Add --execute to send moveJ and gripper_control.")
        return 0

    motion_label = Path(args.name).stem if args.command == "restore" else args.name
    before = snapshot(args.records, f"before_{motion_label}", current)
    print(f"Saved pre-motion snapshot: {before}")
    robot = create_high_level_robot(args.sdk_root)
    try:
        # Do not use iswait=True here: the vendor helper considers a target
        # within its 0.1 rad default tolerance already reached and can return
        # immediately for small corrections. Keep the command active for the
        # requested duration, then give the gripper its own settling interval.
        robot.moveJ(target["joints_rad"], duration=args.duration, iswait=False)
        time.sleep(max(args.duration, 0.2))
        robot.gripper_control(target["gripper_rad"], 0.12, 0.15)
        time.sleep(1.0)
        print(f"Executed pose {args.name!r}; verify feedback before the next action.")
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
