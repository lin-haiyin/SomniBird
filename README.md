<p align="center">
  <img src="assets/images/robot-workstation.jpg" alt="SomniBird onsite workstation" width="72%" />
</p>

<h1 align="center">SomniBird</h1>

<p align="center"><strong>好梦鸟 · A cybernetic sleep companion</strong></p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="https://github.com/lin-haiyin/SomniBird"><img src="https://img.shields.io/badge/status-onsite%20prototype-08a88a?style=flat-square" alt="Onsite prototype" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+" /></a>
  <a href="https://github.com/HighTorque-Robotics/Panthera-HT_Host"><img src="https://img.shields.io/badge/hardware-Panthera--HT-ef6c3b?style=flat-square" alt="Panthera-HT" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-5c7cfa?style=flat-square" alt="MIT License" /></a>
</p>

> A direct-SDK robotics prototype for expressive, interactive sleep-time scenes.

`SomniBird` (好梦鸟) was built during a hackathon around a six-axis Panthera-HT arm. The project explored how a robot arm can communicate a small story through posture, slow motion, gripper timing, and a camera-aware interaction loop rather than through industrial pick-and-place alone.

The work used the **official HighTorque Panthera-HT Python SDK** as its hardware layer. This is an independent prototype, not an official HighTorque product or an endorsed integration.

## What We Built

| Capability | Evidence |
| --- | --- |
| Direct SDK communication | Seven motors (J1-J6 plus gripper) were discovered and read back with zero reported faults during onsite validation. |
| Named rest poses | `sleep` and `sleep2` capture reviewed return postures without changing factory motor zero. |
| Teach and replay workflow | Operator-guided trajectory recording produces JSONL trajectories; replay is separated from scene registration. |
| Expressive scenes | A nod, phone-intervention action, blanket interaction, and plant-like continuous motion were developed as reusable action patterns. |
| USB-camera exploration | OpenCV face detection was isolated from the motion layer as a first step toward conservative 2D tracking. |

<p align="center">
  <img src="assets/images/live-demo.jpg" alt="现场演示中的机械臂与团队" width="45%" />
  <img src="assets/images/team-demo.jpg" alt="团队在现场调试机械臂" width="45%" />
</p>

## Repository Scope

This repository contains the application scripts, configuration examples, and engineering notes created around the prototype. It intentionally does **not** contain:

- the vendor SDK, its configuration files, or firmware;
- recorded trajectories, host credentials, network addresses, model weights, or runtime logs;
- videos and other large raw assets from the event.

The arm host was returned after the event. Consequently, code in this repository is a documented prototype and reference implementation, **not a claim that the full physical setup can be reproduced from this repository alone**.

## Architecture

```text
Operator-guided teaching / scene request
                |
                v
Application actions and scene manager
                |
                +--> named poses / recorded trajectories
                |
                v
Official Panthera-HT Python SDK
                |
                v
Control box -> CAN1 -> 6-axis arm + gripper

USB camera -> OpenCV 2D perception -> conservative scene selection / offset proposal
```

The vision process is intentionally separate from SDK motion output. A detector may identify a face or marker; it should not issue unrestricted joint targets directly.

## Code Map

- `scripts/arm_action.py` - unified teaching, recording, replay, and rest-pose workflow.
- `scripts/plant_mode.py` - continuous, smooth expressive-motion profiles.
- `scripts/gripper_api.py` - reusable gripper open/close/cycle abstraction.
- `scripts/pose_bookmark.py` - named pose capture, preview, and explicit execution.
- `scripts/face_detect_preview.py` - OpenCV-only face detection smoke test; no robot commands.
- `configs/poses.yaml` - reviewed prototype poses in radians.
- `configs/scenes.yaml` - application-facing scene registry.
- `docs/TECHNICAL_ROADMAP.md` - next-stage technical plan and validation gates.

## Rebuilding the Environment

The official SDK is not bundled. After obtaining it from HighTorque, configure this project for the new host rather than restoring the event-machine paths:

```bash
source configs/environment.example.sh
"$PANTHERA_PYTHON" -m pip install -r requirements.txt
"$PANTHERA_PYTHON" scripts/check_connection.py
```

The last command is feedback-only. Do not execute a pose, replay, or plant mode until the arm's wiring, workspace, return pose, and emergency-stop arrangement have been reviewed for that specific installation.

The optional vision relay additionally requires OpenCV and Ultralytics plus locally provisioned model weights; these remain deliberately outside the base dependency list.

## Status and Safety

The project prioritizes the official SDK over ROS and vendor GUI workflows. All physical movement must remain explicitly opt-in and be preceded by communication, feedback, workspace, and emergency-stop checks. Do not use the supplied poses as universal safe values: they were reviewed for one onsite arm setup and one physical orientation only.

See [Prototype Notes](docs/PROTOTYPE_NOTES.md) for verified results and limits, and [Technical Roadmap](docs/TECHNICAL_ROADMAP.md) for the intended next steps.

## Upstream Attribution

- Panthera-HT Host repository: <https://github.com/HighTorque-Robotics/Panthera-HT_Host>
- Panthera-HT documentation hub: <https://hightorque.cn/Panthera-HT_Hub/>

Please obtain the official SDK and follow its license, hardware documentation, and safety requirements before using this code with real hardware. The Panthera-HT name and related marks belong to HighTorque Robotics.

## Media

The included images and videos document the onsite prototype. Their public use was confirmed by the project owner. See [assets/media/README.md](assets/media/README.md) for the asset index.

## License

This project is released under the [MIT License](LICENSE). It covers the original project code and documentation only. Vendor SDKs and third-party models are not redistributed here and retain their own licenses.
