# SteamWorld Heist: Ultimate Edition 2.2.1

Title 010016100A186000, update v65536, SDK 4.5.0. All module IDs match the
registered profile: main d6759070f75cc4c8a5b8ea59f52292a5 and SDK
d95547528dcd684e2813ec83d338a472. Upstream has played the first mission and
verified save/reload on Mac; iPhone gameplay remains untested.

The registered profile is kept with its default 2D virtual pad. Simplified
Chinese is declared by NACP and selected. No frame-rate/cheat patches or runtime
changes are added. The Ultimate Edition's DLC/dlc01-dlc03 directories are in the
base RomFS and are included; there are no separate add-on content NCAs.

## Local preparation and path regression

Windows merges the update and extracts 694 resources. All 25 shaders are in
Bundle/data01.impak (zip). The initial split differed only because Windows
source-label separators changed the package group from bundle to other.
A synthetic Windows-path test reproduced the behavioral failure before the fix.
The local scanner adapter normalizes relative source labels to forward slashes;
its content is part of the preparation cache fingerprint. The test then passed,
and the actual shader map, facts and pair data all match the registered tables.
The upstream scanner and Apple translator/host sources remain unchanged.

## Cloud split and checks

Only the prepared modules, registered profile, shader package, control/icon/NPDM
metadata and a compile-only 4 KiB prefix of the profile marker are uploaded,
compressed and protected by SHA256 plus AES-256-GCM. Original XCI, full resources
and Switch keys stay local. The standard free public xcode-27 workflow compiles
pinned cde88f62068e3d879b083b1a86a7fd78610c7b7b and requires all 25 shaders to
succeed. The unsigned template is encrypted before artifact upload.
Windows replaces its RomFS with all complete local resources, checks every ZIP
CRC, resource size, arm64 executable and execute mode, and records SHA256.
The resulting iOS package still needs physical-device gameplay validation.
