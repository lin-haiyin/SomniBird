#!/usr/bin/env python3
"""统一的 Panthera-HT 手动示教录制与回放入口。

Examples:
  python arm_action.py record sleep_scene1
  python arm_action.py replay sleep_scene1

录制时默认使用重力+摩擦补偿；默认进入和回落到项目中的 sleep2 姿态，可用参数选择其他姿态。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import tempfile
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SDK_ROOT = Path(os.environ.get(
    "PANTHERA_SDK_ROOT", PROJECT_ROOT / "vendor" / "panthera_python"
))
DEFAULT_RECORD_DIR = Path(os.environ.get(
    "PANTHERA_TRAJECTORY_DIR", PROJECT_ROOT / "records" / "trajectories"
))
SLEEP_JOINTS = [0.0] * 6
SLEEP_GRIPPER = 0.0
SLEEP2_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, -math.pi / 2.0]
SLEEP2_GRIPPER = 0.0
POSES_FILE = PROJECT_ROOT / "configs" / "poses.yaml"
SCENES_FILE = PROJECT_ROOT / "configs" / "scenes.yaml"


def clamp_gripper(value: float) -> float:
    """Normalize encoder zero-offset noise to the vendor range [0, 2] rad."""
    return max(0.0, min(2.0, float(value)))


def load_named_pose(name: str) -> tuple[list[float], float]:
    """Load a project pose without touching the robot."""
    with POSES_FILE.open("r", encoding="utf-8") as handle:
        raw = (yaml.safe_load(handle) or {}).get("poses", {}).get(name)
    if not isinstance(raw, dict):
        available = []
        with POSES_FILE.open("r", encoding="utf-8") as handle:
            poses = (yaml.safe_load(handle) or {}).get("poses", {})
            if isinstance(poses, dict):
                available = sorted(poses)
        raise ValueError(f"姿态 {name!r} 不存在；可用姿态：{', '.join(available)}")
    joints = raw.get("joints_rad")
    gripper = raw.get("gripper_rad")
    if not isinstance(joints, list) or len(joints) != 6 or gripper is None:
        raise ValueError(f"姿态 {name!r} 未完整定义")
    values = [float(value) for value in joints]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"姿态 {name!r} 包含无效关节值")
    return values, clamp_gripper(float(gripper))


def scene_pose_defaults(scene_name: str) -> tuple[str, str]:
    """Return configured start/return poses, falling back to the current sleep2."""
    try:
        with SCENES_FILE.open("r", encoding="utf-8") as handle:
            scenes = (yaml.safe_load(handle) or {}).get("scenes", {})
    except FileNotFoundError:
        scenes = {}
    raw = scenes.get(scene_name, {}) if isinstance(scenes, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return str(raw.get("start_pose") or "sleep2"), str(raw.get("return_pose") or "sleep2")


def import_sdk(sdk_root: Path):
    scripts = sdk_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from Panthera_lib import Panthera, TrajectoryRecorder  # type: ignore
    return Panthera, TrajectoryRecorder


def make_robot(sdk_root: Path):
    Panthera, recorder = import_sdk(sdk_root)
    return Panthera(str(sdk_root / "robot_param" / "Follower.yaml")), recorder


def return_sleep(robot, duration: float, gripper_velocity: float = 0.5,
                 gripper_torque: float = 0.5) -> None:
    """Return fully to sleep, including enough repeated gripper commands.

    ``gripper_control`` is a non-blocking setpoint command.  Sending it once
    at 0.12 rad/s and waiting one second cannot close a gripper that was near
    2 rad open, so keep issuing the target for a bounded settling window.
    This is project sleep positioning, not motor-zero calibration.
    """
    print("\n正在回到 sleep 姿态（六轴 0 rad，夹爪 0 rad）...", flush=True)
    robot.moveJ(SLEEP_JOINTS, duration=duration, iswait=False)
    settle_duration = max(float(duration), 4.5)
    deadline = time.monotonic() + settle_duration
    while time.monotonic() < deadline:
        robot.gripper_control(SLEEP_GRIPPER, gripper_velocity, gripper_torque)
        time.sleep(0.05)
    print("已回到 sleep 姿态。", flush=True)


def return_sleep2(robot, duration: float, gripper_velocity: float = 0.5,
                  gripper_torque: float = 0.5) -> None:
    """Move to the independent sleep2 pose without changing record/replay sleep."""
    print("\n正在回到 sleep2 姿态（J6 -π/2 rad，夹爪 0 rad）...", flush=True)
    robot.moveJ(SLEEP2_JOINTS, duration=duration, iswait=False)
    settle_duration = max(float(duration), 4.5)
    deadline = time.monotonic() + settle_duration
    while time.monotonic() < deadline:
        robot.gripper_control(SLEEP2_GRIPPER, gripper_velocity, gripper_torque)
        time.sleep(0.05)
    print("已回到 sleep2 姿态。", flush=True)


def return_named_pose(robot, name: str, duration: float,
                      gripper_velocity: float = 0.5,
                      gripper_torque: float = 0.5) -> None:
    """Smoothly move to any named project pose."""
    joints, gripper = load_named_pose(name)
    print(f"\n正在回到 {name} 姿态...", flush=True)
    robot.moveJ(joints, duration=duration, iswait=False)
    settle_duration = max(float(duration), 4.5)
    deadline = time.monotonic() + settle_duration
    while time.monotonic() < deadline:
        robot.gripper_control(gripper, gripper_velocity, gripper_torque)
        time.sleep(0.05)
    print(f"已回到 {name} 姿态。", flush=True)


def warmup(robot) -> None:
    for _ in range(10):
        robot.send_get_motor_state_cmd()
        time.sleep(0.1)


def record(args: argparse.Namespace) -> int:
    robot, Recorder = make_robot(args.sdk_root)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"{args.name}.jsonl"
    if path.exists() and not args.overwrite:
        raise SystemExit(f"文件已存在：{path}\n如需覆盖，请加 --overwrite")

    # Every recording has the same lifecycle: current pose -> configured entry
    # pose -> teach recording -> Ctrl+C -> configured return pose.
    return_named_pose(robot, args.start_pose, args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
    rec = Recorder(str(path))
    use_friction = args.feel in {"gravity_friction", "adaptive", "soft"}
    assist = args.feel in {"adaptive", "soft"}
    # 示教保持增益，不是回放刚度。adaptive 比 soft 更轻，并且运动时不追旧目标。
    if args.feel == "soft":
        K = [0.8, 1.5, 1.5, 0.4, 0.25, 0.2]
        B = [0.12, 0.18, 0.18, 0.08, 0.04, 0.04]
    else:
        # Adaptive remains hand-teachable, but adds a moderate amount of
        # holding resistance so the arm does not feel completely weightless.
        K = [0.40, 0.70, 0.70, 0.18, 0.12, 0.10]
        B = [0.12, 0.18, 0.18, 0.08, 0.045, 0.045]
    Fc = [0.15, 0.12, 0.12, 0.12, 0.04, 0.04]
    Fv = [0.05, 0.05, 0.05, 0.03, 0.02, 0.02]
    tau_limit = [8.0, 12.0, 12.0, 6.0, 3.0, 3.0]
    q_hold = None
    stable_since = None
    print(f"开始录制场景：{args.name}")
    print(f"手感模式：{args.feel}; 文件：{path}")
    print(f"手动摆动、抓取和放下；完成后按 Ctrl+C，程序会保存并回到 {args.return_pose}。", flush=True)
    warmup(robot)
    next_time = time.perf_counter()
    next_record = next_time
    try:
        while True:
            q = list(map(float, robot.get_current_pos()))
            v = list(map(float, robot.get_current_vel()))
            if assist:
                if q_hold is None:
                    q_hold = q[:]
                speed = max(abs(x) for x in v)
                # 检测到人工移动时立即跟随当前姿态，避免旧目标造成回弹。
                if speed >= 0.02:
                    q_hold = q[:]
                    stable_since = None
                else:
                    if stable_since is None:
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= 0.35:
                        q_hold = q[:]

            gravity = list(map(float, robot.get_Gravity(q)))
            torque = gravity[:]
            if use_friction:
                friction = list(map(float, robot.get_friction_compensation(v, Fc, Fv, 0.02)))
                torque = [a + b for a, b in zip(torque, friction)]
            if assist:
                torque = [
                    max(-limit, min(limit, g + k * (h - x) - b * vel))
                    for g, k, h, x, b, vel, limit in zip(
                        gravity, K, q_hold, q, B, v, tau_limit
                    )
                ]

            robot.pos_vel_tqe_kp_kd([0.0] * 6, [0.0] * 6, torque, [0.0] * 6, [0.0] * 6)
            # The physical encoder can report a tiny negative value around its
            # closed stop (e.g. -0.003 rad). The SDK correctly rejects that
            # command, so recordings use the documented [0, 2] rad range.
            gripper = clamp_gripper(robot.get_current_pos_gripper())
            gripper_vel = float(robot.get_current_vel_gripper())
            robot.gripper_control_MIT(0.0, 0.0, 0.0, 0.0, 0.0)
            now = time.perf_counter()
            if now >= next_record:
                rec.log(q, v, gripper, gripper_vel)
                next_record += args.record_dt
            next_time += args.control_dt
            delay = next_time - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_time = time.perf_counter()
    except KeyboardInterrupt:
        print("\n录制停止。", flush=True)
    finally:
        rec.close()
        try:
            return_named_pose(robot, args.return_pose, args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
        finally:
            stop = getattr(robot, "set_stop", None)
            if callable(stop):
                stop()
    return 0


def replay(args: argparse.Namespace) -> int:
    robot, Recorder = make_robot(args.sdk_root)
    path = Path(args.file)
    if not path.is_absolute():
        path = args.output / path
    if path.suffix != ".jsonl":
        path = path.with_suffix(".jsonl")
    if not path.is_file():
        raise SystemExit(f"轨迹文件不存在：{path}")
    configured_start, configured_return = scene_pose_defaults(path.stem)
    args.start_pose = args.start_pose or configured_start
    args.return_pose = args.return_pose or configured_return
    print(f"开始回放：{path}", flush=True)
    return_named_pose(robot, args.start_pose, args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
    # Older recordings may contain small negative gripper values caused by
    # encoder zero offset. Create a temporary normalized copy for playback.
    normalized = None
    normalized_path = None
    with path.open("r", encoding="utf-8") as source:
        frames = []
        for line in source:
            if not line.strip():
                continue
            frame = json.loads(line)
            if "gripper_pos" in frame:
                frame["gripper_pos"] = clamp_gripper(frame["gripper_pos"])
            frames.append(frame)
    normalized = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".jsonl", delete=False
    )
    normalized_path = Path(normalized.name)
    for frame in frames:
        normalized.write(json.dumps(frame, ensure_ascii=False) + "\n")
    normalized.close()
    try:
        Recorder.play(
            robot=robot,
            filepath=str(normalized_path),
            kp=[30.0, 40.0, 55.0, 15.0, 7.0, 5.0],
            kd=[3.0, 4.0, 5.5, 1.5, 0.7, 0.5],
            fc=[0.15, 0.12, 0.12, 0.12, 0.04, 0.04],
            fv=[0.05, 0.05, 0.05, 0.03, 0.02, 0.02],
            vel_threshold=0.02,
            tau_limit=[15.0, 30.0, 30.0, 15.0, 5.0, 5.0],
            gripper_kp=5.0,
            gripper_kd=0.5,
        )
    except KeyboardInterrupt:
        print("\n回放中止。", flush=True)
    finally:
        try:
            return_named_pose(robot, args.return_pose, args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
        finally:
            stop = getattr(robot, "set_stop", None)
            if callable(stop):
                stop()
            if normalized_path is not None:
                normalized_path.unlink(missing_ok=True)
    return 0


def sleep_command(args: argparse.Namespace) -> int:
    robot, _ = make_robot(args.sdk_root)
    try:
        return_named_pose(robot, "sleep", args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
    finally:
        stop = getattr(robot, "set_stop", None)
        if callable(stop):
            stop()
    return 0


def sleep2_command(args: argparse.Namespace) -> int:
    robot, _ = make_robot(args.sdk_root)
    try:
        return_named_pose(robot, "sleep2", args.sleep_duration, args.sleep_gripper_velocity, args.sleep_gripper_torque)
    finally:
        stop = getattr(robot, "set_stop", None)
        if callable(stop):
            stop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="手动示教并连续录制")
    rec.add_argument("name", help="场景名称，例如 sleep_scene1")
    rec.add_argument("--feel", choices=("gravity", "gravity_friction", "adaptive", "soft"), default="gravity_friction")
    rec.add_argument("--overwrite", action="store_true")
    rec.add_argument("--control-dt", type=float, default=0.002)
    rec.add_argument("--record-dt", type=float, default=0.01)
    rec.add_argument("--sleep-duration", type=float, default=8.0)
    rec.add_argument("--sleep-gripper-velocity", type=float, default=0.5)
    rec.add_argument("--sleep-gripper-torque", type=float, default=0.5)
    rec.add_argument("--start-pose", default="sleep2", help="录制前进入的姿态名称，默认 sleep2")
    rec.add_argument("--return-pose", default="sleep2", help="Ctrl+C 后回到的姿态名称，默认 sleep2")
    rec.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    rec.add_argument("--output", type=Path, default=DEFAULT_RECORD_DIR)
    rec.set_defaults(func=record)
    play = sub.add_parser("replay", help="回放一个已录制场景")
    play.add_argument("file", help="场景名或 .jsonl 文件路径")
    play.add_argument("--sleep-duration", type=float, default=8.0)
    play.add_argument("--sleep-gripper-velocity", type=float, default=0.5)
    play.add_argument("--sleep-gripper-torque", type=float, default=0.5)
    play.add_argument("--start-pose", default=None, help="回放前进入的姿态名称；未指定时使用场景配置，默认 sleep2")
    play.add_argument("--return-pose", default=None, help="回放结束后回到的姿态名称；未指定时使用场景配置，默认 sleep2")
    play.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    play.add_argument("--output", type=Path, default=DEFAULT_RECORD_DIR)
    play.set_defaults(func=replay)
    slp = sub.add_parser("sleep", help="回到项目级 sleep 姿态")
    slp.add_argument("--sleep-duration", type=float, default=8.0)
    slp.add_argument("--sleep-gripper-velocity", type=float, default=0.5)
    slp.add_argument("--sleep-gripper-torque", type=float, default=0.5)
    slp.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    slp.set_defaults(func=sleep_command)
    slp2 = sub.add_parser("sleep2", help="回到独立的 sleep2 姿态（J6 向左 90°，夹爪 0）")
    slp2.add_argument("--sleep-duration", type=float, default=8.0)
    slp2.add_argument("--sleep-gripper-velocity", type=float, default=0.5)
    slp2.add_argument("--sleep-gripper-torque", type=float, default=0.5)
    slp2.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    slp2.set_defaults(func=sleep2_command)
    args = parser.parse_args()
    if args.sleep_gripper_velocity <= 0 or args.sleep_gripper_torque <= 0:
        parser.error("sleep 夹爪速度和力矩必须为正数")
    for pose_name in (getattr(args, "start_pose", None), getattr(args, "return_pose", None)):
        if pose_name is not None:
            try:
                load_named_pose(pose_name)
            except (OSError, ValueError) as exc:
                parser.error(str(exc))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
