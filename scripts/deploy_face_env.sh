#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PANTHERA_PYTHON:-python3}"
MODEL_DIR="$ROOT/models"
MODEL="$MODEL_DIR/face_detection_yunet_2023mar.onnx"
mkdir -p "$MODEL_DIR"

"$PYTHON" -m pip install --upgrade "opencv-python-headless>=4.10,<5" >/tmp/panthera_face_pip.log 2>&1 || {
  echo "OpenCV installation failed; see /tmp/panthera_face_pip.log" >&2
  exit 1
}
if [[ ! -s "$MODEL" ]]; then
  curl -fL --retry 3 -o "$MODEL" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi
"$PYTHON" - <<'PY'
import cv2, numpy
print("opencv", cv2.__version__)
print("numpy", numpy.__version__)
print("FaceDetectorYN", hasattr(cv2, "FaceDetectorYN"))
PY
echo "Face preview environment ready: $ROOT"
