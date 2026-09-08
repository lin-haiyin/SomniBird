#!/usr/bin/env python3
"""Capture one test frame from the GX10 USB camera or its local RTSP stream.

Uses the FFmpeg already installed on GX10; no OpenCV or numpy is required.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_DEVICE = "/dev/v4l/by-id/usb-Insta360_Insta360_Link_2C-video-index0"
DEFAULT_RTSP = "rtsp://127.0.0.1:8554/camera"
DEFAULT_OUTPUT = "/tmp/gx10_camera_test.jpg"


def capture(source: str, output: Path, *, width: int, height: int, fps: int, rtsp: bool) -> None:
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    output.parent.mkdir(parents=True, exist_ok=True)
    if rtsp:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
            "-i", source, "-frames:v", "1", "-q:v", "2", "-y", str(output),
        ]
    else:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "v4l2",
            "-input_format", "mjpeg", "-video_size", f"{width}x{height}",
            "-framerate", str(fps), "-i", source, "-frames:v", "1", "-q:v", "2",
            "-y", str(output),
        ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=20)
    except FileNotFoundError as exc:
        raise SystemExit("找不到 ffmpeg，请确认 GX10 已安装 /usr/local/bin/ffmpeg") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit("抓帧超时：请检查摄像头是否连接或被其他程序占用") from exc
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        detail = (result.stderr or "无 FFmpeg 错误输出").strip()
        raise SystemExit(f"抓帧失败（退出码 {result.returncode}）：{detail}")
    print(f"抓帧成功：{source}")
    print(f"输出文件：{output}（{output.stat().st_size} bytes）")


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 GX10 摄像头并保存一张 JPEG")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="V4L2 摄像头设备路径")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="JPEG 输出路径")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--rtsp", action="store_true", help="从本地 RTSP 流抓帧")
    parser.add_argument("--rtsp-url", default=DEFAULT_RTSP)
    args = parser.parse_args()
    source = args.rtsp_url if args.rtsp else args.device
    capture(source, Path(args.output), width=args.width, height=args.height, fps=args.fps, rtsp=args.rtsp)


if __name__ == "__main__":
    main()
