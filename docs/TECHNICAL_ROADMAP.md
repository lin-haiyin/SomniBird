# Technical Roadmap

## Product Direction

Build a small library of expressive robotic characters that can be repeatedly demonstrated with a six-axis arm and an ordinary USB camera. The near-term objective is not autonomous general-purpose manipulation; it is reliable, legible, and safe scene behavior.

## Stage 1: Recover a Reproducible Hardware Baseline

**Goal:** make the project runnable on a new Panthera-HT host without relying on undocumented event state.

1. Install the official SDK according to its upstream instructions; do not redistribute it in this repository.
2. Parameterize SDK location, trajectory directory, serial/CAN configuration, and camera device through environment variables or a local untracked configuration file.
3. Run state-only motor diagnostics and record arm model, end effector, control-box firmware, and wiring verification.
4. Re-teach `sleep` and `sleep2`; do not copy their values blindly from this prototype.
5. Record versioned trajectories with a metadata sidecar: mounting orientation, payload, gripper state, teaching mode, operator, and scene assumptions.

**Exit criterion:** seven valid motor feedback states, a reviewed return pose, and one low-speed replay that returns predictably.

## Stage 2: Make Scenes Reliable

**Goal:** move from one-off demonstrations to repeatable application actions.

1. Model every scene as `enter -> perform -> recover`, with a timeout and a user-accessible stop path.
2. Store trajectories outside Git or in Git LFS, with a compact JSON metadata file committed alongside code.
3. Add a scene validator: joint-limit check, gripper range check, timestamp monotonicity, and maximum velocity/acceleration review.
4. Add tests for command construction and trajectory parsing that do not require a connected arm.
5. Add a small simulator or visual pose preview for code review before physical execution.

**Exit criterion:** a scene catalog can be previewed, validated, invoked by name, interrupted, and returned to a reviewed rest pose.

## Stage 3: Use a USB Camera Conservatively

**Goal:** use vision to select and modulate a known scene, not to invent unrestricted trajectories.

1. Calibrate the camera to a fixed work plane using ArUco/AprilTag markers or a printed board.
2. Detect face direction, hand position, or a tagged prop in 2D.
3. Map image observations to bounded scene choices or small reviewed offsets around a nominal pose.
4. Define explicit loss behavior: hold, slowly return to rest, or stop. Never continue using stale image coordinates.
5. Log confidence, target identity, and selected action without retaining personal imagery by default.

**Exit criterion:** a person can change which prevalidated scene is selected or cause a small bounded character response; invalid/low-confidence vision sends no movement.

## Stage 4: Add Contact-Aware Interaction

**Goal:** make simple props more tolerant to modest variation without pretending monocular vision solves 3D grasping.

1. Define fixtures, known prop zones, and limits on object size/weight.
2. Use gripper current/torque feedback where the official SDK supports it to detect gentle contact.
3. Add a retry policy with bounded attempts, a retreat waypoint, and an operator-visible failure state.
4. Consider a depth camera or wrist force sensing only when the product needs unstructured 3D grasping.

**Exit criterion:** an interaction with a constrained prop can report success/failure, recover safely, and avoid repeating a failed motion indefinitely.

## Recommended Demonstration Set

| Scene | Why it is feasible early |
| --- | --- |
| Plant sway | Pure joint choreography; no object geometry required. |
| Nod / attention response | Clear character motion with modest, bounded joint changes. |
| Face-direction response | USB-camera 2D tracking can select left/right attention poses after calibration. |
| Phone intervention | Works with a fixed prop location and a taught trajectory. |
| Blanket pull | Works as a fixed-stage choreography, but needs fixtures and a consistent fabric starting state. |

## What Not to Promise Yet

- arbitrary object grasping from a single uncalibrated USB camera;
- transferring a taught scene to a materially different table height or object placement;
- autonomous recovery from unknown collisions;
- direct use of a detector output as an unrestricted joint command.
