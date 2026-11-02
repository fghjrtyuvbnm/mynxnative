# Uncharted Waters IV: local preparation and free Apple compilation

Target: `0100F0E0136BE000`, update v131072 / 1.0.2, main build
`b0af08523e1f31067bb9e170532047ac`, SDK 10.4.1. Upstream source:
`cde88f62068e3d879b083b1a86a7fd78610c7b7b`.

## Division of work

- Windows: XCI integrity check; base/update merging; architecture and import survey;
  provisional profile; rewriting main, sdk and eight registered NROs; extraction
  of all 17 shader programs; hashing, compression and authenticated encryption.
- Public GitHub Actions: standard `xcode-27` Apple Silicon runner, Xcode 27.2;
  pinned shader translator/Metal toolchain; unsigned iOS application compilation.
- Windows: decrypt the compiled template, add all 221 complete RomFS files,
  preserve Unix executable permissions, check all ZIP CRCs and produce SHA256.

This follows the Windows/cloud split used by the user's FFR reference project.
The newer source requires Xcode 27.2 rather than the FFR source's older toolchain.
The free hosted preflight has passed architecture, SDK and synthetic iOS Metal
compilation checks. It does not test the game's runtime.

## Local work

Game-derived files and portable .NET/Python tools stay in the game's work folder
beside the original XCI. Never place keys or extracted game files in this repo.
Run local preparation with Python UTF-8 mode:

```text
python -X utf8 scripts/prepare_uncharted_local.py <XCI> <game-work> --keys <prod.keys>
```

On Windows the script uses the source-built nx_extract.exe and upstream's
`DM_REWRITE_J=1` setting, which avoids fork while preserving rewrite behavior.
The survey previously treated a directory named `.nro` as a module; the script
now filters for files. This was reproduced on this image before the one-line
repair, and the same survey passed afterward. This is real-image regression
evidence; no synthetic import failure is counted as test-first evidence.

## Reference game and profile

Taiko Risshiden V DX (`0100346017304000`) is a useful input/memory reference.
This binary also imports GetTouchScreenState, GetGestureStates and CPU overclock
state, and its NPDM declares zero system resource. Its own heap analysis gives
4 GB reservation, 256 MB alias and stack regions, and app pool 0xCD500000.
The provisional profile starts in handheld touch mode. No foreign game's fixed
instruction address, frame-rate cut, shader table or build ID is copied.

Unlike that reference title, this title loads eight NRO modules at runtime.
They are collected against the NRR registrations and rewritten locally.
The cloud marker is the real 752-byte `res/GlobalConfig.ktsl2gcbin`, included in
the complete local RomFS too; the 119 MB TownGrp resource need not be uploaded.

## Encrypted transfer

The prepared archive is 6,189,914 bytes before the 36-byte AES-GCM envelope.
It contains 88 hashed inputs, no original XCI, no Switch keys and no full RomFS.
A local authenticated pack/restore round trip verifies every input SHA256.

Because the Release upload endpoint times out on this connection, encrypted
input blocks are stored under `build-input/` in the public configuration repo.
The workflow restores their ordered ciphertext and authenticates it before
extracting. `BUILD_CIPHER_KEY` is the only Actions Secret required. The local
key is `local-private/build.key`, a gitignored file. Keep it backed up securely.
No `prod.keys` is uploaded. The public repository exposes ciphertext and build
configuration; never commit the local key or plaintext prepared archive.

The compiled app template is AES-256-GCM encrypted before artifact upload.
Artifact `UnchartedWatersIV-encrypted-template` expires after one day. Download
and extract it locally, then finish:

```text
python -X utf8 scripts/finish_uncharted_local.py <template.ipa.enc> <game-work> <new-output.ipa> --key-file local-private/build.key
```

The finalizer refuses an existing output, checks the bundle and arm64 Mach-O,
preserves template modes and shader files, adds complete local resources,
checks all ZIP CRCs, and writes `<output>.verification.json` with SHA256.
Its synthetic-template round trip has passed. Tests added after implementation
are regression coverage, not a claimed RED/GREEN cycle.

## Limits

The output is unsigned. No signing or installation is automated. No physical
Apple device or game runtime has been tested. Rendering, input, sound, saves,
memory suitability and frame rate remain unverified. Use Documents/log.txt
from the installed app to investigate runtime issues. The cloud build must
compile all 17 discovered shaders; it does not silently accept missing ones.

## Completed build

The free hosted build succeeded:
https://github.com/fghjrtyuvbnm/mynxnative/actions/runs/41373666294

Local assembly produced `UnchartedWatersIV-1.0.2-unsigned.ipa`:
1,522,409,061 bytes, 221 complete RomFS files, all ZIP CRCs checked,
arm64 executable mode 0755 preserved, minimum iOS/iPadOS 26.0. The launcher
was checked for handheld mode and Simplified Chinese defaults. No frame-rate
patch is applied. Main and all eight NRO cut tables contain no game-specific
cuts; SDK cuts concern address-region memory layout.

SHA256: `584e7aeca7c6132f2b46fc67c59a6790aaa0f4581d5d5352630e8cd7cce1115d`.
Physical-device gameplay remains untested.

## Later frame-rate patch review

The user later asked to check whether a frame-rate patch could also be used here.
The two reviewed Taiko frame-end function rules match no function in main build
b0af08523e1f31067bb9e170532047ac. A direct-import/call survey finds different
GetSystemTick/SleepThread timing code, but does not establish an equivalent
safe frame-end cut. No verified dedicated patch was located. Therefore the
existing Uncharted Waters IV IPA remains unchanged and without a frame-rate
patch. This is a finding about the available verified patch, not proof that
no custom patch could ever be developed. Runtime frame-time evidence is needed
before changing an unrelated timing loop.
