#!/usr/bin/env python3
"""Preview-only face detection for the ordinary USB camera.

This script deliberately does not import Panthera_lib and never sends a motion
command. It is the first perception smoke test before adding a tracking state
machine. YuNet's ONNX model is downloaded separately by deploy_face_env.sh.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path


def parse_source(value: str):
    return int(value) if value.isdigit() else value


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview YuNet face detection only")
    parser.add_argument("--source", default="0", help="V4L2 device path or camera index")
    parser.add_argument("--model", default="models/face_detection_yunet_2023mar.onnx")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--save", type=Path, help="Save the latest annotated frame")
    parser.add_argument("--no-window", action="store_true", help="Run without GUI; print detections")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("OpenCV is not installed; run deploy_face_env.sh first") from exc

    model = Path(args.model)
    if not model.is_absolute():
        model = Path(__file__).resolve().parents[1] / model
    if not model.exists():
        raise SystemExit(f"YuNet model not found: {model}")

    source = parse_source(args.source)
    # V4L2 is required for a device node; RTSP uses OpenCV's FFmpeg backend.
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG if isinstance(source, str) and source.startswith("rtsp") else cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera: {args.source}")

    detector = cv2.FaceDetectorYN.create(str(model), "", (args.width, args.height), 0.75, 0.3, 5000)
    print("Preview only. No Panthera SDK or motion command is used. Press q or Ctrl+C to stop.")
    last_print = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera_read_failed")
                time.sleep(0.2)
                continue
            detector.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = detector.detect(frame)
            count = 0 if faces is None else len(faces)
            if time.monotonic() - last_print >= 0.5:
                if count:
                    boxes = [tuple(round(float(x), 1) for x in face[:4]) for face in faces]
                    print(f"faces={count} boxes(x,y,w,h)={boxes}")
                else:
                    print("faces=0")
                last_print = time.monotonic()
            if faces is not None:
                for face in faces:
                    x, y, w, h = (int(v) for v in face[:4])
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 0), 2)
                    cv2.circle(frame, (x + w // 2, y + h // 2), 4, (0, 0, 255), -1)
            if args.save:
                args.save.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(args.save), frame)
            if not args.no_window:
                cv2.imshow("YuNet face preview (no motion)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
