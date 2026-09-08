# GitHub Publishing Checklist

## Before Making the Repository Public

- [ ] Confirm that all identifiable people in `assets/images/` consent to public sharing.
- [ ] Decide whether the event name, booth artwork, and visible QR code can be published.
- [ ] Select a repository name and a short description.
- [x] Release original project code and documentation under the MIT License. It does not cover the HighTorque SDK or any third-party model.
- [ ] Check `git status --ignored` after Git is initialized and confirm that `records/`, `runtime/`, `models/`, and raw videos are ignored.
- [ ] Search again for addresses, tokens, passwords, and private endpoints before the first push.

## Suggested Repository Metadata

**Name:** `SomniBird`

**Description:** `A direct-SDK Panthera-HT hackathon prototype for expressive robotic interaction, teaching/replay, and conservative USB-camera perception.`

**Topics:** `robotics`, `robot-arm`, `python`, `computer-vision`, `opencv`, `hackathon`, `human-robot-interaction`, `panthera-ht`

## Suggested First Commit

```text
docs: publish SomniBird Panthera-HT hackathon prototype
```

## Recommended Video Handling

Keep the raw event videos out of Git history. Choose one of these after reviewing privacy/permission:

1. Upload a short edited demo to a video platform and link it from the README.
2. Attach a compressed MP4 to a GitHub Release.
3. Use Git LFS only if source-quality video is genuinely part of the project artifact.

## Attribution Language

Use this wording in the repository description or README:

> Built as an independent prototype using the official HighTorque Panthera-HT Python SDK. It is not an official HighTorque project or endorsed integration.

This gives appropriate credit without implying affiliation. Link to the upstream repository and documentation, but do not copy the SDK into this repository unless its license permits redistribution.
