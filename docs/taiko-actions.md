# Taiko Risshiden V DX 1.1.3: patched private-input/free-runner build

Title `0100346017304000`; combined XCI includes base, v262144 update and DLC
`0100346017305001`. Main build `d9120950c258610a746f4a31ce3a3b37`.
The user initially requested no frame-rate patch, then explicitly requested
using the patch. The final build must include the validated frame limiter cut.

## Frame limiter validation

The upstream opt-in function rule from `dm/games/0100346017304000/patches.py`
uniquely matches implementation 1 on this build, with the cut at `main+0x4444dc`.
Complete function/callee fingerprints and the original 20 bytes are checked.
The local rewriter's main.cuts.tsv records exactly this one cut. No guessed
address is used. It sets the wait threshold to zero only for N=1 and preserves
the original waiting logic for N=2, per the upstream reviewed rule.

The previously published 55-to-60 fps measurement applies to upstream's 1.1.1,
not a physical-device measurement of this 1.1.3 build. Enabled patch status
must not be represented as verified gameplay frame rate.

## Work split and transfer

Windows merges the update, extracts 1324 full RomFS files and the 196,634,958-byte
DLC image, rewrites main/subsdk0/sdk, and splits 212 shaders. The shader key set
and pair table match the upstream 1.1.1 profile. A source copy in this game's
work folder retains the upstream patch rules for the local rewrite.

Only 38 compilation inputs are compressed with LZMA and AES-256-GCM encrypted.
The archive is 7,490,364 bytes before encryption. It contains no Switch keys,
original XCI, full RomFS or DLC. An authenticated restore verifies every input
SHA256. Ciphertext blocks under build-input-taiko/ are checked by Git object
hash before publication; BUILD_CIPHER_KEY is the only secret required.

The public workflow build-taiko-ipa.yml uses standard free xcode-27 runners
and pinned upstream source cde88f62068e3d879b083b1a86a7fd78610c7b7b. It demands
all 212 shaders compile and requires the expected frame limiter cut metadata.
The compiled template is encrypted before artifact upload (one-day retention).
Windows adds the complete original resources and DLC, checks every ZIP CRC,
resource size, arm64 header and executable mode, then records output SHA256.
A synthetic local template/base/DLC assembly test has passed.

## Limits

The result is unsigned. No physical-device gameplay, input, audio, saves,
DLC behavior, frame rate or power consumption is verified by compilation.
The default language is Simplified Chinese and input is handheld touch.

## Completed build

Free hosted build succeeded:
https://github.com/fghjrtyuvbnm/mynxnative/actions/runs/41375749509

Local output: TaikoRisshidenVDX-1.1.3-fps-patch-unsigned.ipa, 3,721,183,192 bytes.
SHA256: b837b2545ca6f970610fd3a351de4aeafb40a90adea7f950f5bb40b47dfc555d.
All 1324 RomFS files and the 196,634,958-byte DLC image are present. Every ZIP
CRC and resource size passed. The arm64 executable retains Unix mode 0755;
the validated 20-byte frame patch sequence occurs exactly once in the final
packaged executable. Minimum iOS/iPadOS is 26.0, handheld and Simplified Chinese
defaults confirmed from the packaged launcher settings. The matching tool's
25 unit tests passed. Actual frame rate and physical-device gameplay remain
untested. The original Uncharted Waters IV IPA retains its prior SHA256.
