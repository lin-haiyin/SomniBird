#!/usr/bin/env python3
"""Reusable application-layer interface for the Panthera gripper (motor ID 7)."""

from __future__ import annotations

import math
import time
from typing import Any


class GripperController:
    """Wrap the vendor ``gripper_control`` call as named open/close actions.

    The controller does not create or own the robot connection. Pass an already
    initialized official ``Panthera`` instance so an application can reuse one
    SDK connection for many actions.
    """

    def __init__(self, robot: Any, *, open_rad: float = 2.0, close_rad: float = 0.0,
                 open_vel: float = 0.5, close_vel: float = 0.5,
                 max_tqu: float = 0.5, dwell: float = 4.0) -> None:
        self.robot = robot
        self.open_rad = float(open_rad)
        self.close_rad = float(close_rad)
        self.open_vel = float(open_vel)
        self.close_vel = float(close_vel)
        self.max_tqu = float(max_tqu)
        self.dwell = float(dwell)
        self._validate()

    def _validate(self) -> None:
        if not 0.0 <= self.close_rad <= 2.0:
            raise ValueError("close_rad must be within the gripper's 0..2 rad limit")
        if not 0.0 <= self.open_rad <= 2.0:
            raise ValueError("open_rad must be within the gripper's 0..2 rad limit")
        if self.open_rad < self.close_rad:
            raise ValueError("open_rad must be greater than or equal to close_rad")
        if self.open_vel <= 0.0 or self.close_vel <= 0.0:
            raise ValueError("open_vel and close_vel must be positive")
        if self.max_tqu <= 0.0 or self.dwell < 0.0:
            raise ValueError("max_tqu must be positive and dwell cannot be negative")

    def open(self, *, dwell: float | None = None) -> None:
        """Move the gripper to the configured open position."""
        self.robot.gripper_control(self.open_rad, self.open_vel, self.max_tqu)
        time.sleep(self.dwell if dwell is None else max(0.0, float(dwell)))

    def close(self, *, dwell: float | None = None) -> None:
        """Move to the configured close position; avoid prolonged hard-stop force."""
        self.robot.gripper_control(self.close_rad, self.close_vel, self.max_tqu)
        time.sleep(self.dwell if dwell is None else max(0.0, float(dwell)))

    def cycle(self, cycles: int = 1) -> None:
        """Perform ``open -> close`` the requested number of times."""
        if int(cycles) != cycles or cycles < 1:
            raise ValueError("cycles must be a positive integer")
        for _ in range(int(cycles)):
            self.open()
            self.close()

    def set_open_position(self, value: float) -> None:
        """Change the open target for later calls, validating the new range."""
        self.open_rad = float(value)
        self._validate()

    def set_close_position(self, value: float) -> None:
        """Change the close target for later calls, validating the new range."""
        self.close_rad = float(value)
        self._validate()


def gripper_open_close(robot: Any, *, cycles: int = 1, open_rad: float = 2.0,
                       close_rad: float = 0.0, open_vel: float = 0.5,
                       close_vel: float = 0.5, max_tqu: float = 0.5,
                       dwell: float = 4.0) -> None:
    """One-call convenience API for application code."""
    GripperController(
        robot,
        open_rad=open_rad,
        close_rad=close_rad,
        open_vel=open_vel,
        close_vel=close_vel,
        max_tqu=max_tqu,
        dwell=dwell,
    ).cycle(cycles)


def degrees(rad: float) -> float:
    """Human-facing conversion helper for UI/logging."""
    return math.degrees(rad)
