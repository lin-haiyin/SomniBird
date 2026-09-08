#!/usr/bin/env python3
"""Use the GX10 offline YOLO models and relay annotated camera frames to RTMP.

All frames stay in memory. This process only reads the existing camera stream
and never imports or calls the Panthera arm SDK.
"""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="rtsp://127.0.0.1:8554/camera")
    p.add_argument("--output", default=os.environ.get(
        "VISION_RTMP_OUTPUT", "rtmp://127.0.0.1:1935/camera"
    ))
    p.add_argument("--detect-model", type=Path, default=Path("/models/yolo/yolo26n.pt"))
    p.add_argument("--pose-model", type=Path, default=Path("/models/yolo/yolo26n-pose.pt"))
    p.add_argument("--face-model", type=Path, default=Path("/models/face_detection_yunet_2023mar.onnx"))
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--device", default="0")
    args = p.parse_args()

    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Vision relay dependencies are optional. Install opencv-python and "
            "ultralytics before running this script."
        ) from exc

    for model in (args.detect_model, args.pose_model):
        if not model.is_file():
            raise FileNotFoundError(model)
    detect = YOLO(str(args.detect_model), task="detect")
    pose = YOLO(str(args.pose_model), task="pose")
    face = None
    if args.face_model.is_file() and hasattr(cv2, "FaceDetectorYN"):
        face = cv2.FaceDetectorYN.create(str(args.face_model), "", (args.width, args.height), 0.75, 0.3, 5000)
    names = detect.names if isinstance(detect.names, dict) else dict(enumerate(detect.names))
    wanted = [i for i, name in names.items() if str(name) in {"person", "cell phone"}]
    cap = cv2.VideoCapture(args.input, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {args.input}")
    ffmpeg = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-f", "rawvideo", "-pix_fmt", "bgr24",
              "-s", f"{args.width}x{args.height}", "-r", str(args.fps), "-i", "-", "-an", "-c:v", "libx264",
              "-preset", "veryfast", "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-b:v", "1200k",
              "-maxrate", "1500k", "-bufsize", "2400k", "-g", str(args.fps * 2), "-f", "flv", args.output]
    out = subprocess.Popen(ffmpeg, stdin=subprocess.PIPE)
    print(f"GX10 models relay: {args.input} -> {args.output}", flush=True)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("camera_read_failed")
            if frame.shape[1] != args.width or frame.shape[0] != args.height:
                frame = cv2.resize(frame, (args.width, args.height))
            result = detect.predict(frame, device=args.device, classes=wanted, verbose=False)[0]
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                    label = str(names[int(box.cls[0].item())])
                    conf = float(box.conf[0].item())
                    color = (60, 220, 60) if label == "person" else (20, 170, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
            pose_result = pose.predict(frame, device=args.device, verbose=False)[0]
            if pose_result.keypoints is not None and pose_result.keypoints.xy is not None:
                plotted = pose_result.plot()
                frame = cv2.addWeighted(frame, 0.55, plotted, 0.45, 0)
            face_count = 0
            if face is not None:
                face.setInputSize((args.width, args.height))
                _, faces = face.detect(frame)
                face_count = 0 if faces is None else len(faces)
                if faces is not None:
                    for item in faces:
                        x, y, w, h = (int(v) for v in item[:4])
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 80, 180), 2)
            cv2.putText(frame, f"GX10 vision | faces={face_count}", (20, 34), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
            out.stdin.write(frame.tobytes())
    except (BrokenPipeError, OSError, RuntimeError) as exc:
        print(f"relay stopped: {exc}", flush=True)
        return 1
    finally:
        cap.release()
        if out.stdin:
            out.stdin.close()
        out.terminate()
        out.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
