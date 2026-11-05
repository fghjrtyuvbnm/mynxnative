# Breath of the Wild 1.6.0: external-data package

The user's XCI contains application `01007EF00011E000`, update v786432
(display version 1.6.0), and DLC `01007EF00011F001` / `01007EF00011F002`,
both v196608. The original image stays on D:. Extraction initially used the exFAT F: drive
while D: lacked headroom. After the user freed D:, all 41,125 frozen work files
(16,834,943,390 bytes) were copied and SHA-256 verified before removing the F:
copy. The active work directory is now
`D:\Users\xly\Downloads\roms\switch\01007EF00011E000-work`.

The registered [game note](../dm/games/01007EF00011E000/README.md) describes
1.9.0. This release uses different modules:

- main: `8e9978d50bdd20b4c8395a106c27ffde`
- subsdk0: `93ff8252d975adf07230cb86c83301c5`
- sdk: `fcf93a41b08c5193a1410d262602dc62` (SDK 7.3.2)

The derived profile regenerates shader tables from this release and both DLC
images. Newer fixed-address game patches and frame-step stubs are not applied;
`fps_target` is zero, preserving the game's own timing. The base/update RomFS
contains 41,052 files totaling 15,128,950,129 bytes. DLC index 1 is a
1,390,238,714-byte image; index 2 is a 127-byte empty image, retained as supplied.
Simplified Chinese is supported by the original control data.

## Local preparation and finalization

`scripts/prepare_botw_local.py` performs extraction, both DLC images, module
rewrite and a complete shader scan. The Windows profile-path correction is
described in [external drive paths](reference/rewriter.md#external-profiles-on-windows-drive-paths).
Its two regression tests failed before the fix and passed afterward; existing
profile tests passed too. The fix uses the platform's path-list separator and
does not change Unix profile lookup.
The existing RomFS metadata and bounded-read regressions also reproduced invalid
Windows image paths before correction and passed afterward. Four image-reader
checks plus an interleaved binary-reader check pass, including scanner equivalence and damaged flags. One check needs
the unavailable `zstd` executable; another reaches an existing Windows repeat-IPA
packing failure (`pack_ipa.py` uses `os.pread`), outside this Mac-cloud packaging
path. That packer is unchanged. These Windows-only access fixes do not change
Unix profile lists or positioned reads; full Mac gameplay regression is not
available on this host.

`scripts/stage_botw.py` hashes every full resource, including both DLC images,
and encrypts only modules, profile and split shader inputs for the public
workflow. Complete game data and Switch keys stay local. The build uses pinned
source `cde88f62068e3d879b083b1a86a7fd78610c7b7b` and the existing external-data
launcher and lifecycle tests. Outputs are encrypted and unsigned.

`scripts/finish_botw.py` validates IPA identity, shader records and all full
resource hashes before moving the verified RomFS and DLC directories into the
final data directory. It avoids duplicating the full game on exFAT. A failure
rolls moved directories back; if rollback itself fails, recoverable resources
remain outside the temporary directory. The exFAT duplicate-resource regression
was RED before the change. Four finalizer checks now pass: successful assembly,
hash failure without moves, failed second move with rollback, and failed
rollback preserving recoverable bytes. Local preparation and staging can reuse
the final data directory after assembly.

Install the IPA, choose the entire data folder and use **Import all data** for
offline use. **Clear game data** retains saves and launcher settings. Actual
iPhone startup, DLC availability and gameplay remain unverified.

The complete base/update and DLC scan took 39 minutes 25 seconds with three
Windows workers and found 19,420 shaders without reader errors. The last
16-file batch dominated the tail. All 41,054 complete local resource records
were hashed (16,519,188,970 bytes); the encrypted cloud input is 38,283,944
bytes. GitHub run `41974157478` builds those inputs.

## Consolidated final data and motion controls

The finalizer now follows the shared compact output policy in
[external data](resonance-external-data.md#compact-output-policy): one
`romfs.img`, `shaders.pack`, `game-data.json`, `aoc/1.img` and `aoc/2.img`.
All 41,052 base/update files are verified inside the image before their loose
copies are removed. Both DLC images and the complete shader pack are retained.
The matching IPA receives the new manifest digest and the default-on **Use
device gyroscope** toggle. No shader translation or executable rebuild is
needed for these data and launcher-configuration changes. Local preparation
and staging can read the final image directly on subsequent builds.

The original missing-toggle and loose-data regressions were RED before the
implementation. Local finalizer coverage also checks failed IPA installation
restoring the original pair, directory DLC conversion, loose shader packing
in manifest order and idempotent consolidation. macOS lifecycle and settings
tests use synthetic resources in run `42000306148`; iPhone gameplay remains
untested. The pinned host returns no SevenSixAxis samples, so standard six-axis
input support does not establish compatibility with every motion puzzle.
