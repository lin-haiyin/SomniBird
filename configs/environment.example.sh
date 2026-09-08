#!/usr/bin/env bash
# Copy values into your shell or an untracked local file before running against
# a real arm. These paths are deliberately not committed as machine-specific
# deployment configuration.

# Official SDK root containing scripts/Panthera_lib.py and robot_param/.
export PANTHERA_SDK_ROOT="/path/to/panthera_python"

# Python interpreter with the official SDK dependencies installed.
export PANTHERA_PYTHON="python3"

# Keep taught trajectories out of the public repository by default.
export PANTHERA_TRAJECTORY_DIR="$PWD/records/trajectories"

# Optional local endpoints for vision relays.
export FACE_RTMP_OUTPUT="rtmp://127.0.0.1:1935/camera_ai"
export VISION_RTMP_OUTPUT="rtmp://127.0.0.1:1935/camera"
