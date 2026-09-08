# Prototype Notes

## Project Context

SomniBird (好梦鸟) was an onsite hackathon prototype using a Panthera-HT six-axis arm as an expressive character. The design question was not simply whether the arm could complete a grasp. It was whether a fixed set of readable movements could communicate an interaction around sleep, a phone, a blanket, or a plant-like character.

## Verified Onsite

- The direct official SDK reached and read all seven motors: six arm joints and the gripper.
- The working physical connection was motor 1 to control-box CAN1.
- Joint feedback was available and the observed fault state was `0x00` for all seven motors during the recorded diagnostics.
- An operator-approved all-zero encoder pose was used as `sleep`; a second rest posture, `sleep2`, rotates J6 by 90 degrees for a vertical gripper orientation.
- Direct-SDK actions were exercised for rest poses, an expressive nod, phone intervention, gripper cycles, teaching/replay, and a plant-like continuous movement concept.
- The USB-camera environment reached an OpenCV face-detection preview. Vision did not autonomously control arm motion.

## Engineering Decisions

| Decision | Reason |
| --- | --- |
| Direct vendor SDK | Faster path to validated hardware feedback and motion primitives than introducing ROS during a short event. |
| Teach before automation | A person can demonstrate a scene and retain timing/pose data before attempting camera-driven behavior. |
| Named poses | `sleep`, `sleep2`, and character poses give application-level language to otherwise numeric joint states. |
| Isolated vision | A normal USB camera provides 2D image coordinates, not reliable distance. Its first responsibility is target selection, not unconstrained motion planning. |
| Explicit motion | Preview, feedback checks, and an operator-accessible stop path remain necessary even for an expressive prototype. |

## Limits

- The returned host machine, vendor SDK installation, recorded JSONL trajectories, and camera deployment are not included here.
- A recorded trajectory only works reliably when the real scene is sufficiently similar to the taught scene. It is not imitation learning with generalized object understanding.
- A monocular USB camera cannot directly infer safe 3D grasp positions without calibration and additional assumptions.
- Pose values and gripper limits are setup-specific. They must be reviewed again on another arm, mounting orientation, or end effector.

## Portfolio Claim

The defensible claim is: *developed and field-tested a direct-SDK interaction prototype, including pose-based scenes, teaching/replay tooling, gripper primitives, and an isolated 2D camera-perception path.*

It would not be accurate to claim a production-grade autonomous grasping system, generalized imitation learning, or a fully reproducible public hardware package.
