# Into the Breach 1.2.88 (experimental iOS package)

Title 010057D00B612000, update v589824 over the base game, no DLC.
Main build ffd0078f805bf3dc13c281319095f8e7 and SDK
3644a6760469451cabc99f00c540acc2 (SDK 13). No matching local upstream
profile/gameplay validation was found; the profile comes from the merged image.
No frame-rate or cheat patches are requested or added. The default 2D pad and
Simplified Chinese language are selected. No runtime or translator changes.

Windows performs the survey, merges the update, extracts 627 resource files,
rewrites main/sdk, refreshes static module memory sizing and splits five loose
GLSLC shader outputs. The scan finished without RED/unreadable files. The
prepared archive contains only the generated profile, rewritten modules, real
shader package, control/icon/NPDM metadata and a compile-only 4 KiB prefix of
resources/resource.dat. Full resources, original XCI and Switch keys stay local.
Per-file SHA256 and AES-256-GCM protect the uploaded inputs.

The standard free public xcode-27 workflow compiles pinned upstream source
cde88f62068e3d879b083b1a86a7fd78610c7b7b. All five discovered shaders must
compile successfully. The unsigned template is encrypted before artifact upload.
Windows replaces all template RomFS entries with complete local resources,
verifies every ZIP CRC, file sizes, arm64 executable and execute mode, and
records output SHA256. Min OS and selected language are reviewed in Info.plist.
Device runtime compatibility is untested. Do not sign/install automatically.

This task copies the established packaging wrappers without changing product
behavior; product RED/GREEN and broad runtime regression suites do not apply.
Validation uses syntax/workflow checks, encrypted restore, actual compiler output,
resource completeness and a synthetic assembly check.
