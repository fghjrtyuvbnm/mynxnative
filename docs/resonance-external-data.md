# FFR Asia: separate launcher and external game data

Target: `0100B8A026F14000`, update v65536 / 1.0.1, main build `b7f965b9d7227db8e29f04e84ea7331b`.

Reuse the existing external-directory template from the user's reference repository,
release `unsigned-template-40482789385`. Its SHA-256 is
`7e1be4b7e85a90ccfbd264fc8c78ff7f7eef4773bee74cddb2a1d1f4124b33fd`.
The result manifest reports all 73,496 shader entries compiled, with no failures.
This avoids a new cloud build and does not mix libraries between shader chains.
Template identity: chain `d374e783beec`, inputs `087b5d58cc3d`.
The original build used nxnative `cdc6cef6b0250fcb54a061e4c55d56382b5d18ad`.
The exporter helpers in `scripts/resonance_export/` are retained unchanged from
reference tree `2b8a06dcf824899ada6ee56cb8988e305f3e6f55`.

## Local preparation and export

Run `scripts/prepare_resonance_local.py IMAGE WORK --keys PROD_KEYS --tools TOOLS`.
It verifies the container's base/update/DLC identities, extracts complete merged
RomFS and DLC locally, and checks all three module build IDs. The `extract/v1`
label is the reference exporter's historical name for v65536, not update version 1.

Download the release's three template parts and `result-manifest.json` to a fresh
folder beside the game. Verify every part against the manifest. Run
`scripts/finish_resonance_local.py DOWNLOAD WORK OUTPUT_IPA`.
The finalizer requires the exact template digest, matching local module identity,
compiled shader coverage and byte-identical DLC. It checks executable architecture
and permissions, exports all resources and verifies every data file's SHA-256.

Outputs are an unsigned launcher IPA and `FFRS-Data/` beside it. The data folder
contains `game-data.json`, `romfs/`, `msl/` and `aoc/`. Shader libraries are part of
the external data. Executable code, host tables and fonts stay inside the IPA.
Resources on NTFS may use hard links to avoid a duplicate local copy; treat the
export as read-only. Copying the folder to another drive copies its complete data.

## Use on iOS

Copy the complete `FFRS-Data` folder to a drive visible in the Files app. Install
the unsigned launcher with the user's usual sideloading method. Open the launcher,
choose **Choose data folder**, select `FFRS-Data` itself, wait for validation, then
press **Play**. The folder opens in place; resources are not imported into the app.
The selection is remembered and can be changed before Play. If a drive is absent or
folder access expires, reconnect it and select the folder again.

Launchers with **Import all data** can also play offline. Select and validate the
matching external folder, then choose **Import all data** and wait for the
offline-ready message before disconnecting the drive. The import verifies the
RomFS and DLC against the manifest, reuses the verified local shader cache, and
commits the local directory only after validation succeeds. Repeating the import
reuses the installed files.

**Clear game data** removes imported files, the local shader cache, the saved
external-folder selection and game-generated scratch files, logs and pipeline
caches. It retains saves, launcher settings and `Documents/env.txt`. The
selected external folder remains available for a later import.

When playing directly from the external folder, keep the drive attached throughout gameplay. Saves, logs and temporary files stay
in the application's Documents directory. Do not place only the XCI on the drive:
the launcher reads the exported directory. A disk must be mounted and readable by
iOS; physical Type-C access and LiveContainer's directory authorization require a
real-device test. No device runtime, rendering, audio or save compatibility is
established by the build checks.

The largest exported resource is 5,976,850,224 bytes. FAT32 cannot hold this file;
exFAT is suitable for copying between Windows and iOS. Apple's supported external
storage formats and connection requirements are documented in
[Connect external storage devices to iPhone](https://support.apple.com/guide/iphone/iph95baac91f/ios).
The complete data files total 12,279,166,314 bytes before filesystem overhead.

## Validation scope

The original FFR export reused existing runtime behavior; no runtime implementation
changed in that export, so a new RED/GREEN behavior cycle did not apply. The reference exporter's four
focused tests (`python -m unittest discover -s scripts/tests -p test_resonance_export.py -v`)
cover separate output/reuse, corrupt data rejection, legacy-template
rejection and hostile archive paths. Validate the actual exported artifact with
SHA-256, ZIP CRC, module IDs, shader identity and DLC content checks. Historical
Swift directory-lifecycle tests passed in reference run `40465149526`; these are
previous evidence, not a fresh Swift test run on this Windows host.

## OpenGL data directories

The shared external-data runtime also accepts a shader directory at `msl/gl/`,
with its compiled library, shader table and `inputs.tsv` identity stamp. NVN data
keeps its existing `msl/b-<chain>/` layout. The manifest must select exactly one
supported layout and all shader records must belong to it. This does not change
the manifest schema or the import/cache locations. Packed OpenGL shaders use the
same verified import, reuse, offline access and save-preserving clear operations.

On 2026-11-05, the new OpenGL lifecycle test failed against the original runtime
with `invalidManifest` while the existing NVN lifecycle suite passed (run
`41943276143`). After the prefix handling change, both suites passed in run
`41943575703`, including rejection of mixed NVN/OpenGL shader records. Five local
NVN manifests (Taiko, Unicorn Overlord Asia, Octopath II, Triangle Strategy and
FFR Asia) retain the expected single-prefix layout. Full `regress.py check`
execution is unavailable on the Windows host (`fcntl` is missing), and these
checks do not establish five-game Mac gameplay or real-device runtime behavior.

## Compact output policy

New external packages must use `romfs.img`, one `shaders.pack` and numbered
`aoc/<index>.img` images, alongside `game-data.json`. Do not distribute a loose
RomFS or a loose shader directory. `scripts/compact_external_data.py` implements
the finalization step shared by the current external finishers, including FFR.
It compares every image entry against the original resource manifest, preserves
shader record order, and binds the revised manifest to the unsigned IPA. It
removes loose source directories only after committing the verified images and
the matching IPA/manifest pair. Recovery backups survive a failed rollback.
The image is an indexed, uncompressed filesystem read directly by the host;
it does not expand back into thousands of files when imported on the device.

The iOS Controls section defaults **Use device gyroscope** to on
(`DM_PHONE_MOTION=1`). Off selects `auto`, restoring controller/phone selection.
Explicit environment-file locks still apply. The shared pinned-source overlay
installs this setting; existing unsigned final outputs receive the same JSON
row without changing their executable or shader chain.

Synthetic macOS tests in run `42000306148` cover both loose and image-layout
full import, no duplicate copies, offline access and save-preserving clear,
plus actual launcher-model default, toggle persistence and reset. They do not
replace real-device motion or game testing. Existing exported games are not
silently converted by this policy; their IPA and data must be updated together
when consolidation is requested.
