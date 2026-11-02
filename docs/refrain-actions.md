# Labyrinth of Refrain TC 1.0.2 (experimental iOS package)

Title 010055F00B5F6000, update v131072, five DLC indices 1-5. Main build
e0ad503c787fec18be91467cbbef6205, SDK af7348498c7759b0f3f0396a8a36014c
(SDK 4). No existing local upstream profile or gameplay validation is available.
The profile is generated from the actual merged image. No frame-rate or cheat
patches are added. The NACP's Traditional Chinese language is selected.

## Local shader inputs

The initial upstream scan found zero shaders. FAFULLFS data.dat contains seven
YKCMP type-7 zlib effect members, with NMPL_FX_SHADERDT payloads. Individual
NMPL_NVN..SHADER descriptors hold a 0x30-byte header, reflection length,
control/code offsets and lengths. All ranges, control magic, code length and
stage are validated. Main embeds the same records. Its 0x848-byte controls can
end at addresses eight bytes short of the next 16-byte boundary; no guessed
adjacent code region is accepted. Each code pointer comes from its descriptor.

The local-only adapter scripts/split_nis_shaders.py extends the pinned scanner
in its process; upstream shader translation tools and host source are unchanged.
FAFULLFS layout was cross-checked against
https://github.com/HybridEidolon/makaikit/blob/master/fafullfs/src/lib.rs .
The preparation cache includes the adapter's file content. A synthetic embedded
vertex/pixel test failed with zero stages before implementation, then passed.
Additional tests cover archive bounds, truncated/overlapping NMPL regions and
exact zlib lengths. The shared prepared-memory regression also passes.

The successful actual scan found 7,075 distinct shaders without RED/unreadable
files. This is offline extraction evidence, not gameplay validation. Five small
110-byte DLC RomFS images are kept so the host can enumerate their ownership.

## Build and verification

Full data.dat/data_sound.dat and Switch keys remain local. Only prepared modules,
shader packages, generated profile, control/icon metadata, five tiny DLC images
and a compile-only 4 KiB resource marker prefix enter the encrypted archive.
Per-file SHA256 and AES-256-GCM protect the inputs. The free standard public
xcode-27 runner compiles pinned cde88f62068e3d879b083b1a86a7fd78610c7b7b,
requires every shader to succeed, and encrypts the unsigned template artifact.
Windows appends the full two DAT resources and all five DLC images, validates
ZIP CRCs/resource sizes/arm64 execute mode, and records output SHA256.
Device runtime behavior remains untested. Do not sign or install automatically.

Additional scanner fixtures: 33/34 pass with the adapter loaded. The remaining
assertion expects /sub/a.dict but Windows emits /sub\\a.dict. It fails identically
in a clean process using only the untouched upstream scanner; it is a verified
pre-existing platform assertion, not a newly introduced reader failure.
