#!/usr/bin/env python3
"""管理已示教轨迹：登记、检查、查看和显式回放。"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("需要 PyYAML：python -m pip install pyyaml") from exc


ROOT = Path(__file__).resolve().parents[1]
TRAJECTORY_DIR = ROOT / "records" / "trajectories"
SCENES_FILE = ROOT / "configs" / "scenes.yaml"
ARM_ACTION = ROOT / "scripts" / "arm_action.py"
PLANT_MODE = ROOT / "scripts" / "plant_mode.py"
LOWER = [-2.4, 0.0, 0.0, -1.6, -1.7, -2.5]
UPPER = [2.4, 3.2, 4.0, 1.6, 1.7, 2.5]


def scene_path(name: str) -> Path:
    path = Path(name)
    if path.suffix != ".jsonl":
        path = path.with_suffix(".jsonl")
    return path if path.is_absolute() else TRAJECTORY_DIR / path


def load_scenes() -> dict:
    if not SCENES_FILE.exists():
        return {"scenes": {}}
    with SCENES_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {"scenes": {}}


def read_frames(path: Path) -> list[dict]:
    frames = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {line_no} 行不是合法 JSON：{exc}") from exc
            frames.append(frame)
    return frames


def inspect(path: Path) -> tuple[dict, list[str], list[str]]:
    frames = read_frames(path)
    errors: list[str] = []
    warnings: list[str] = []
    if len(frames) < 2:
        errors.append("轨迹至少需要 2 帧")
        return {}, errors, warnings
    previous_t = -math.inf
    all_pos = [[] for _ in range(6)]
    grip = []
    max_step = 0.0
    previous_pos = None
    for index, frame in enumerate(frames):
        t = float(frame.get("t", math.nan))
        pos = frame.get("pos")
        if not isinstance(pos, list) or len(pos) != 6:
            errors.append(f"第 {index + 1} 帧 pos 不是 6 个关节值")
            continue
        if not math.isfinite(t) or t < previous_t:
            errors.append(f"第 {index + 1} 帧时间戳不递增")
        previous_t = t
        for joint, value in enumerate(pos):
            value = float(value)
            if not math.isfinite(value):
                errors.append(f"第 {index + 1} 帧 J{joint + 1} 不是有限值")
                continue
            all_pos[joint].append(value)
            if value < LOWER[joint] - 0.05 or value > UPPER[joint] + 0.05:
                warnings.append(f"J{joint + 1} 有点位接近/超出官方范围：{value:.4f} rad")
        if previous_pos is not None:
            max_step = max(max_step, max(abs(a - b) for a, b in zip(pos, previous_pos)))
        previous_pos = [float(x) for x in pos]
        if "gripper_pos" in frame:
            value = float(frame["gripper_pos"])
            if not math.isfinite(value):
                errors.append(f"第 {index + 1} 帧夹爪不是有限值")
            elif value < -0.001 or value > 2.001:
                warnings.append(f"夹爪值超出 [0,2]，回放时会限制：{value:.4f}")
            grip.append(max(0.0, min(2.0, value)))
    duration = float(frames[-1].get("t", 0.0)) - float(frames[0].get("t", 0.0))
    summary = {
        "frames": len(frames),
        "duration_s": round(duration, 3),
        "max_joint_step_rad": round(max_step, 5),
        "start_pos": frames[0].get("pos"),
        "end_pos": frames[-1].get("pos"),
        "gripper_min": round(min(grip), 5) if grip else None,
        "gripper_max": round(max(grip), 5) if grip else None,
    }
    if max_step > 0.15:
        warnings.append(f"相邻采样最大关节变化 {max_step:.3f} rad，建议检查是否有丢帧")
    return summary, sorted(set(errors)), sorted(set(warnings))


def cmd_list(_: argparse.Namespace) -> int:
    scenes = load_scenes().get("scenes", {})
    files = sorted(TRAJECTORY_DIR.glob("*.jsonl")) if TRAJECTORY_DIR.exists() else []
    for path in files:
        name = path.stem
        meta = scenes.get(name, {}) if isinstance(scenes, dict) else {}
        print(f"{name}: {meta.get('description', '未登记')}")
    if not files:
        print("暂无轨迹")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = scene_path(args.scene)
    if not path.is_file():
        raise SystemExit(f"轨迹不存在：{path}")
    summary, errors, warnings = inspect(path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for item in warnings:
        print("警告：" + item)
    for item in errors:
        print("错误：" + item)
    return 1 if errors else 0


def cmd_register(args: argparse.Namespace) -> int:
    path = scene_path(args.scene)
    if not path.is_file():
        raise SystemExit(f"轨迹不存在：{path}")
    summary, errors, warnings = inspect(path)
    if errors:
        raise SystemExit("轨迹检查失败：" + "；".join(errors))
    data = load_scenes()
    data.setdefault("scenes", {})[path.stem] = {
        "description": args.description,
        "trajectory": path.name,
        "frames": summary["frames"],
        "duration_s": summary["duration_s"],
        "validated": True,
    }
    with SCENES_FILE.open("w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(data, f, allow_unicode=False, sort_keys=False)
    print(f"已登记场景：{path.stem}")
    for item in warnings:
        print("警告：" + item)
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    path = scene_path(args.scene)
    if not path.is_file():
        raise SystemExit(f"轨迹不存在：{path}")
    summary, errors, warnings = inspect(path)
    if errors:
        raise SystemExit("回放前检查失败：" + "；".join(errors))
    print(f"场景：{path.stem}，{summary['duration_s']} 秒，{summary['frames']} 帧")
    for item in warnings:
        print("警告：" + item)
    if not args.execute:
        print("预览模式：未发送运动命令。确认环境后加 --execute 才会回放。")
        return 0
    return subprocess.call([sys.executable, str(ARM_ACTION), "replay", str(path)])


def cmd_plant(args: argparse.Namespace) -> int:
    """Control the continuous procedural plant scene."""
    command = [sys.executable, str(PLANT_MODE), args.action, "--profile", args.profile]
    if args.action == "start":
        for option in ("period", "j1_total", "j2_total", "j3_total", "j5_total", "j5_delay", "gripper_open", "gripper_close", "gripper_velocity", "enter_duration", "sleep_duration"):
            value = getattr(args, option, None)
            if value is not None:
                command.extend([f"--{option.replace('_', '-')}", str(value)])
    return subprocess.call(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    val = sub.add_parser("validate"); val.add_argument("scene"); val.set_defaults(func=cmd_validate)
    reg = sub.add_parser("register"); reg.add_argument("scene"); reg.add_argument("description"); reg.set_defaults(func=cmd_register)
    rep = sub.add_parser("replay"); rep.add_argument("scene"); rep.add_argument("--execute", action="store_true"); rep.set_defaults(func=cmd_replay)
    for profile in ("plant", "plant2"):
        plant = sub.add_parser(profile, help=f"持续{profile}动作：启动、停止或查看状态")
        plant.add_argument("action", choices=("start", "stop", "status"))
        plant.add_argument("--period", type=float)
        plant.add_argument("--j1-total", dest="j1_total", type=float)
        plant.add_argument("--j2-total", dest="j2_total", type=float)
        plant.add_argument("--j3-total", dest="j3_total", type=float)
        plant.add_argument("--j5-total", dest="j5_total", type=float)
        plant.add_argument("--j5-delay", dest="j5_delay", type=float)
        plant.add_argument("--gripper-open", dest="gripper_open", type=float)
        plant.add_argument("--gripper-close", dest="gripper_close", type=float)
        plant.add_argument("--gripper-velocity", dest="gripper_velocity", type=float)
        plant.add_argument("--enter-duration", dest="enter_duration", type=float)
        plant.add_argument("--sleep-duration", dest="sleep_duration", type=float)
        plant.set_defaults(func=cmd_plant, profile=profile)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
