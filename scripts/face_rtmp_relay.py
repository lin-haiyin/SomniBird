#!/usr/bin/env python3
"""In-memory YuNet face overlay relay: local RTSP -> public RTMP.

No image/video is written to disk. This process never imports the Panthera SDK
and never sends CAN or motion commands.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="rtsp://127.0.0.1:8554/camera")
    ap.add_argument("--output", default=os.environ.get(
        "FACE_RTMP_OUTPUT", "rtmp://127.0.0.1:1935/camera_ai"
    ))
    ap.add_argument("--model", default="models/face_detection_yunet_2023mar.onnx")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    import cv2

    model = Path(args.model)
    if not model.is_absolute():
        model = Path(__file__).resolve().parents[1] / model
    if not model.exists():
        raise SystemExit(f"YuNet model not found: {model}")

    detector = cv2.FaceDetectorYN.create(str(model), "", (args.width, args.height), 0.75, 0.3, 5000)
    ffmpeg = [
        "/usr/local/bin/ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{args.width}x{args.height}",
        "-r", str(args.fps), "-i", "-", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
        "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2400k", "-g", str(args.fps * 2),
        "-f", "flv", args.output,
    ]

    while True:
        cap = cv2.VideoCapture(args.input, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            print("input_open_failed; retrying", flush=True)
            time.sleep(2)
            continue
        proc = subprocess.Popen(ffmpeg, stdin=subprocess.PIPE)
        print(f"face relay started: {args.input} -> {args.output}", flush=True)
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("camera_read_failed")
                if frame.shape[1] != args.width or frame.shape[0] != args.height:
                    frame = cv2.resize(frame, (args.width, args.height), interpolation=cv2.INTER_LINEAR)
                detector.setInputSize((args.width, args.height))
                _, faces = detector.detect(frame)
                count = 0 if faces is None else len(faces)
                if faces is not None:
                    for face in faces:
                        x, y, w, h = (int(v) for v in face[:4])
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 0), 3)
                        cv2.circle(frame, (x + w // 2, y + h // 2), 6, (0, 0, 255), -1)
                cv2.putText(frame, f"faces: {count}", (24, 42), cv2.FONT_HERSHEY_SIMPLEX,
                            1.0, (0, 220, 0), 2, cv2.LINE_AA)
                proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, RuntimeError, OSError) as exc:
            print(f"face relay reconnect: {exc}", flush=True)
        finally:
            cap.release()
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
