#!/usr/bin/env python3
"""HTTP scene service for the Panthera-HT application layer."""

from __future__ import annotations

import datetime as dt
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "arm_action.py"
PLANT_SCRIPT = PROJECT_ROOT / "scripts" / "plant_mode.py"
PYTHON = Path(os.environ.get("PANTHERA_PYTHON", sys.executable))
TRAJECTORY_DIR = Path(os.environ.get(
    "PANTHERA_TRAJECTORY_DIR",
    PROJECT_ROOT / "records" / "trajectories",
))
PORT = int(os.environ.get("PANTHERA_HTTP_PORT", "8000"))

app = Flask(__name__)
lock = threading.Lock()
process: subprocess.Popen | None = None
job: dict = {"state": "idle", "scene": None, "pid": None, "started_at": None, "returncode": None, "output": ""}


@app.after_request
def _add_cors_headers(response):
    """Allow the standalone control page/ESP web UI to call this API."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _refresh() -> None:
    global process
    with lock:
        if process is None:
            return
        code = process.poll()
        if code is not None:
            job["state"] = "completed" if code == 0 else "failed"
            job["returncode"] = code
            process = None


def _start(command: list[str], scene: str | None = None) -> dict:
    global process, job
    _refresh()
    with lock:
        if process is not None:
            raise RuntimeError("已有动作正在运行")
        process = subprocess.Popen(
            command, cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        job = {
            "state": "running", "scene": scene, "pid": process.pid,
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "returncode": None, "output": "",
        }
        return dict(job)


def _command(*args: str) -> list[str]:
    return [str(PYTHON), str(SCRIPT), *args]


def _plant_cli(action: str, profile: str = "plant") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(PLANT_SCRIPT), action, "--profile", profile], cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=10,
    )


def _run_recorded_scene(name: str):
    """Start one of the application-approved one-shot recorded scenes."""
    path = TRAJECTORY_DIR / f"{name}.jsonl"
    if not path.is_file() or path.parent != TRAJECTORY_DIR:
        return jsonify({"error": f"场景不存在或尚未部署: {name}"}), 404
    for profile in ("plant", "plant2"):
        if "running" in _plant_cli("status", profile).stdout:
            return jsonify({"error": f"{profile} 正在运行，请先停止持续场景"}), 409
    try:
        result = _start(_command("replay", name), name)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"scene": name, "mode": "one_shot", **result}), 202


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "panthera-scene-service"})


@app.get("/api/scenes")
def scenes():
    names = sorted(path.stem for path in TRAJECTORY_DIR.glob("*.jsonl"))
    return jsonify({"scenes": names, "directory": str(TRAJECTORY_DIR)})


@app.get("/api/status")
def status():
    _refresh()
    with lock:
        result = dict(job)
    result["running"] = result["state"] == "running"
    return jsonify(result)


@app.post("/api/scenes/<name>/replay")
def replay_scene(name: str):
    path = TRAJECTORY_DIR / f"{name}.jsonl"
    if not path.is_file() or path.parent != TRAJECTORY_DIR:
        return jsonify({"error": f"场景不存在: {name}"}), 404
    try:
        result = _start(_command("replay", name), name)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 202


@app.post("/api/application/blanket01/run")
def application_blanket01():
    return _run_recorded_scene("blanket01")


@app.post("/api/application/insert02/run")
def application_insert02():
    return _run_recorded_scene("insert02")


@app.post("/api/application/take_phone02/run")
def application_take_phone02():
    return _run_recorded_scene("take_phone02")


@app.post("/api/application/shake_toy02/run")
def application_shake_toy02():
    return _run_recorded_scene("shake_toy02")


@app.post("/api/scenes/plant/start")
def plant_start():
    result = _plant_cli("start", "plant")
    if result.returncode != 0:
        return jsonify({"error": result.stderr or result.stdout}), 409
    return jsonify({"scene": "plant", "state": "starting", "message": result.stdout.strip()}), 202


@app.post("/api/scenes/plant/stop")
def plant_stop():
    result = _plant_cli("stop", "plant")
    if result.returncode != 0:
        return jsonify({"error": result.stderr or result.stdout}), 409
    return jsonify({"scene": "plant", "state": "stopping", "message": result.stdout.strip()})


@app.get("/api/scenes/plant/status")
def plant_status():
    result = _plant_cli("status", "plant")
    return jsonify({"scene": "plant", "state": "running" if "running" in result.stdout else "stopped", "message": result.stdout.strip()}), (200 if result.returncode == 0 else 500)


@app.post("/api/arm/stop")
def stop():
    plant_results = [_plant_cli("stop", profile) for profile in ("plant", "plant2")]
    plant_message = " ".join(result.stdout.strip() for result in plant_results if result.stdout.strip())
    _refresh()
    with lock:
        if process is None:
            return jsonify({"state": job["state"], "message": plant_message or "当前没有运行中的动作"})
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        return jsonify({"state": "stopping", "pid": process.pid})


@app.post("/api/arm/sleep")
def sleep():
    try:
        result = _start(_command("sleep"), "sleep")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 202


@app.post("/api/arm/sleep2")
def sleep2():
    """Move to the independent J6-left-90° rest pose."""
    try:
        result = _start(_command("sleep2"), "sleep2")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result), 202


@app.post("/api/application/plant2/start")
def application_plant2_start():
    _refresh()
    with lock:
        if process is not None:
            return jsonify({"error": "已有一次性动作正在运行，请先等待完成或调用 /api/arm/stop"}), 409
    result = _plant_cli("start", "plant2")
    if result.returncode != 0:
        return jsonify({"error": result.stderr or result.stdout}), 409
    return jsonify({"scene": "plant2", "mode": "continuous", "state": "starting", "message": result.stdout.strip()}), 202


@app.post("/api/application/plant2/stop")
def application_plant2_stop():
    result = _plant_cli("stop", "plant2")
    if result.returncode != 0:
        return jsonify({"error": result.stderr or result.stdout}), 409
    return jsonify({"scene": "plant2", "mode": "continuous", "state": "stopping", "message": result.stdout.strip()})


@app.get("/api/application/plant2/status")
def application_plant2_status():
    result = _plant_cli("status", "plant2")
    running = "running" in result.stdout
    return jsonify({"scene": "plant2", "mode": "continuous", "state": "running" if running else "stopped", "message": result.stdout.strip()}), (200 if result.returncode == 0 else 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
