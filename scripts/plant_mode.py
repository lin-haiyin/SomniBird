#!/usr/bin/env python3
"""Continuous procedural plant sway mode with start/stop/status commands."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSES_FILE = PROJECT_ROOT / "configs" / "poses.yaml"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DEFAULT_SDK_ROOT = Path(os.environ.get(
    "PANTHERA_SDK_ROOT", PROJECT_ROOT / "vendor" / "panthera_python"
))


def profile_paths(profile: str) -> tuple[Path, Path, Path]:
    """Return isolated PID/state/log files for plant or plant2."""
    suffix = "" if profile == "plant" else "2"
    return (
        RUNTIME_DIR / f"plant_mode{suffix}.pid",
        RUNTIME_DIR / f"plant_mode{suffix}.json",
        RUNTIME_DIR / f"plant_mode{suffix}.log",
    )


def load_pose(name: str) -> tuple[list[float], float]:
    with POSES_FILE.open("r", encoding="utf-8") as handle:
        raw = (yaml.safe_load(handle) or {}).get("poses", {}).get(name)
    if not isinstance(raw, dict) or not isinstance(raw.get("joints_rad"), list):
        raise RuntimeError(f"姿态 {name!r} 不存在或未保存")
    joints = [float(value) for value in raw["joints_rad"]]
    if len(joints) != 6:
        raise RuntimeError(f"姿态 {name!r} 必须包含 6 个关节值")
    return joints, float(raw.get("gripper_rad", 0.0))


def write_state(state_file: Path, state: str, **extra: object) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "pid": os.getpid(), "updated_at": time.time(), **extra}
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def existing_pid(pid_file: Path) -> int | None:
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def import_robot(sdk_root: Path):
    scripts = sdk_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from Panthera_lib import Panthera  # type: ignore
    return Panthera(str(sdk_root / "robot_param" / "Follower.yaml"))


def send(robot, q: list[float], gripper: float, gripper_velocity: float,
         kp: list[float], kd: list[float]) -> None:
    torque = list(map(float, robot.get_Gravity(q)))
    if robot.pos_vel_tqe_kp_kd(q, [0.0] * 6, torque, kp, kd) is False:
        raise RuntimeError("SDK 拒绝了关节控制目标")
    if robot.gripper_control(gripper, gripper_velocity, 0.15) is False:
        raise RuntimeError("SDK 拒绝了夹爪控制目标")


def smooth_move(robot, start: list[float], target: list[float], duration: float,
                gripper: float, gripper_velocity: float, kp: list[float],
                kd: list[float], stop_event: Event) -> list[float]:
    begin = time.perf_counter()
    current = start[:]
    while True:
        u = min(1.0, (time.perf_counter() - begin) / duration)
        blend = 0.5 - 0.5 * math.cos(math.pi * u)
        current = [a + (b - a) * blend for a, b in zip(start, target)]
        send(robot, current, gripper, gripper_velocity, kp, kd)
        if u >= 1.0 or stop_event.is_set():
            return current
        time.sleep(0.01)


def run(args: argparse.Namespace) -> int:
    pid_file, state_file, _ = profile_paths(args.profile)
    plant, plant_gripper = load_pose(args.profile)
    return_pose_name = "sleep2" if args.profile == "plant2" else "sleep"
    return_pose, return_gripper = load_pose(return_pose_name)
    robot = import_robot(args.sdk_root)
    stop_event = Event()

    def request_stop(signum, _frame):
        print(f"收到停止信号 {signum}，将停止摆动并回到 sleep", flush=True)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    kp = [24.0, 32.0, 42.0, 10.0, 5.0, 4.0]
    kd = [3.0, 4.0, 5.0, 1.2, 0.6, 0.5]
    write_state(state_file, "starting", profile=args.profile, period_s=args.period)
    current = list(map(float, robot.get_current_pos()))
    try:
        print(f"平滑进入 {args.profile} 姿态...", flush=True)
        current = smooth_move(robot, current, plant, args.enter_duration, plant_gripper, args.gripper_velocity, kp, kd, stop_event)
        if not stop_event.is_set():
            write_state(state_file, "running", profile=args.profile, period_s=args.period, amplitudes_deg={"j1": args.j1_total, "j2": args.j2_total, "j3": args.j3_total, "j5": args.j5_total})
            a1, a2, a3, a5 = (math.radians(value / 2.0) for value in (args.j1_total, args.j2_total, args.j3_total, args.j5_total))
            started = time.perf_counter()
            while not stop_event.is_set():
                elapsed = time.perf_counter() - started
                phase = 2.0 * math.pi * elapsed / args.period
                target = plant[:]
                target[0] += a1 * math.sin(phase)
                target[1] += a2 * math.sin(phase)
                target[2] += a3 * math.sin(phase)
                delayed = max(0.0, elapsed - args.j5_delay)
                target[4] += a5 * math.sin(2.0 * math.pi * delayed / args.period)
                # Smooth 0.0 -> open -> 0.0 gripper motion once per sway cycle.
                # The cosine profile starts and ends closed, avoiding a jump at
                # the moment the plant mode enters its first cycle.
                gripper = args.gripper_close + (args.gripper_open - args.gripper_close) * (0.5 - 0.5 * math.cos(phase))
                send(robot, target, gripper, args.gripper_velocity, kp, kd)
                current = target
                time.sleep(0.01)
        write_state(state_file, "stopping", profile=args.profile)
        print(f"平滑回到 {return_pose_name} 姿态...", flush=True)
        smooth_move(robot, current, return_pose, args.sleep_duration, return_gripper, args.gripper_velocity, kp, kd, Event())
        write_state(state_file, "stopped", profile=args.profile, return_pose=return_pose_name)
        print(f"已回到 {return_pose_name}。", flush=True)
        return 0
    finally:
        stop = getattr(robot, "set_stop", None)
        if callable(stop):
            stop()
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass


def start(args: argparse.Namespace) -> int:
    # Validate named poses before spawning: otherwise the shell reports
    # "started" while the child immediately exits with a traceback.
    try:
        load_pose(args.profile)
        load_pose("sleep")
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"无法启动 {args.profile}：{exc}")
        print(f"请先保存 {args.profile} 姿态：python scripts/pose_bookmark.py save-current {args.profile}")
        return 2
    pid_file, _, log_file = profile_paths(args.profile)
    other_profile = "plant2" if args.profile == "plant" else "plant"
    other_pid = existing_pid(profile_paths(other_profile)[0])
    if other_pid is not None:
        print(f"无法启动 {args.profile}：{other_profile} 模式正在运行（PID={other_pid}），请先停止它")
        return 3
    pid = existing_pid(pid_file)
    if pid is not None:
        print(f"{args.profile} 模式已在运行，PID={pid}")
        return 0
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--profile", args.profile, "--sdk-root", str(args.sdk_root), "--period", str(args.period), "--j1-total", str(args.j1_total), "--j2-total", str(args.j2_total), "--j3-total", str(args.j3_total), "--j5-total", str(args.j5_total), "--j5-delay", str(args.j5_delay), "--gripper-open", str(args.gripper_open), "--gripper-close", str(args.gripper_close), "--gripper-velocity", str(args.gripper_velocity), "--enter-duration", str(args.enter_duration), "--sleep-duration", str(args.sleep_duration)]
    with log_file.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=str(PROJECT_ROOT), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pid_file.write_text(str(process.pid) + "\n", encoding="utf-8")
    print(f"{args.profile} 模式已启动，PID={process.pid}，日志：{log_file}")
    return 0


def stop(args: argparse.Namespace) -> int:
    pid_file, _, _ = profile_paths(args.profile)
    pid = existing_pid(pid_file)
    if pid is None:
        print(f"当前没有运行中的 {args.profile} 模式")
        return 0
    os.kill(pid, signal.SIGTERM)
    print(f"已发送停止请求（PID={pid}）；程序将平滑回到 sleep")
    return 0


def status(args: argparse.Namespace) -> int:
    _, state_file, _ = profile_paths(args.profile)
    pid = existing_pid(profile_paths(args.profile)[0])
    if pid is None:
        print(f"{args.profile}: stopped")
        return 0
    print(f"{args.profile}: running (PID={pid})")
    if state_file.exists():
        print(state_file.read_text(encoding="utf-8").strip())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "run", "stop", "status"))
    parser.add_argument("--profile", choices=("plant", "plant2"), default="plant")
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--period", type=float, default=2.20)
    parser.add_argument("--j1-total", type=float, default=10.0)
    parser.add_argument("--j2-total", type=float, default=8.0)
    parser.add_argument("--j3-total", type=float, default=8.0)
    parser.add_argument("--j5-total", type=float, default=35.0)
    parser.add_argument("--j5-delay", type=float, default=0.5)
    parser.add_argument("--gripper-open", type=float, default=2.0)
    parser.add_argument("--gripper-close", type=float, default=0.0)
    parser.add_argument("--gripper-velocity", type=float, default=1.0)
    parser.add_argument("--enter-duration", type=float, default=8.0)
    parser.add_argument("--sleep-duration", type=float, default=10.0)
    args = parser.parse_args()
    if args.period <= 0 or min(args.j1_total, args.j2_total, args.j3_total, args.j5_total) < 0:
        parser.error("周期必须为正，摆幅不能为负")
    if not 0.0 <= args.gripper_close <= 2.0 or not 0.0 <= args.gripper_open <= 2.0:
        parser.error("夹爪开合值必须在 0.0 到 2.0 rad 之间")
    if args.gripper_velocity <= 0:
        parser.error("夹爪速度必须为正")
    return {"start": start, "run": run, "stop": stop, "status": status}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
