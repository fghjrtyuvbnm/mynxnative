# 13 Sentinels: Aegis Rim Asia 1.00

Title 01008D7016438000, base v0. All three module build IDs must match the
registered Asia profile before rewriting. The Western reference is a different
main build; its addresses are never copied. Keep alloc_big_align on, depth_mode
zero, the 4 GiB guest layout and default 2D pad. No frame-rate or cheat patches.

Windows extracts the full three CPK archives, rewrites the registered modules,
refreshes static module memory sizing and checks split shader tables against the
registered profile. Full resources and Switch keys remain local. Cloud inputs
include only prepared modules, shader packages, profile, control metadata and
the actual 4 KiB prefix of ROBO_CN.CPK as an existence marker. This prefix is
compile-only: DM_COPY_ROMFS=NO excludes it from the template. The finalizer
replaces all template resource entries with the complete local CPK archives.

The archive has per-file SHA256 verification and AES-256-GCM encryption. Only
ciphertext chunks are published. The standard xcode-27 public Actions runner
compiles Metal and an unsigned arm64 template from pinned upstream source
cde88f62068e3d879b083b1a86a7fd78610c7b7b. All discovered shaders must compile.
The template is encrypted before artifact upload with one-day retention.

Windows verifies the artifact, decrypts it, streams complete resources into a
ZIP64 IPA and checks ZIP CRCs, resource sizes, arm64 executable and execute mode.
The verification sidecar records final size and SHA256. Do not sign or install.
Upstream has played the Asia build on Mac; this IPA still needs device testing.

Local preparation found 751 shaders and all registered shader tables matched.
AES round-trip and 37 input file hashes passed. Synthetic finalization verified
three complete resources replace the compile marker without duplicate ZIP paths,
while shader bytes and executable mode survive. The shared prepared-memory
regression also passes. These checks do not establish device gameplay.
