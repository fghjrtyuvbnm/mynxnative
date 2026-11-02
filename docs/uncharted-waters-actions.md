# Uncharted Waters IV: free public Actions build

This repository holds build configuration only. The workflow checks out
`seedds/nxnative` at `cde88f62068e3d879b083b1a86a7fd78610c7b7b`.
It uses the standard `xcode-27` hosted runner in a public repository.
No paid larger runner is requested.

## Inputs and output

- Release attachments (16 MiB parts): AES-256-GCM encrypted XCI, never the original game.
- Actions variable `GAME_XCI_ASSET_IDS`: JSON array of ordered encrypted attachment IDs.
- Actions secret `BUILD_CIPHER_KEY`: 32-byte AES key encoded as hex.
- Actions secret `PROD_KEYS`: the user's own Switch keys as text.
- Artifact: `UnchartedWatersIV-encrypted-ipa`, retained for one day.

The encrypted input's original SHA256 must be
`0c8f01e3969357c0968bc8443166f1d33b1cdfffca46455d304f0d0f3325542b`.
The local source was 1,511,003,136 bytes. Keys and original game files must
never be committed or uploaded as public attachments. Secrets must only be
used by trusted workflow code. Only manual dispatch is configured.

## Retrieve the IPA

Download and extract the encrypted artifact, then decrypt locally:

```powershell
python scripts/ipa_crypto.py decrypt UnchartedWatersIV.ipa.enc UnchartedWatersIV.ipa --key-file local-private/build.key
```

Install Python `cryptography` if needed. Keep `local-private/build.key` backed
up securely: losing it prevents decryption. This folder is gitignored in the
local working copy. The cloud has the key only through Actions Secrets.
AES-GCM uses a fresh random nonce per encryption and rejects tampering.

## Verification limits

The IPA is unsigned. Container verification does not establish game
compatibility. This title has no upstream profile, so the build guesses one.
`--no-heap-check` skips the physical Mac probe unavailable on the hosted VM;
`--gpu none` omits optional offline pipeline archives. Startup, memory sizing
and rendering require physical-device testing. The app writes diagnostics to
`Documents/log.txt`. No signing or device installation is automated.

Local checks cover empty, short and multi-block encryption round trips,
tampering rejection, preserving an existing output after authentication
failure, and workflow/embedded Python syntax. A completed cloud run is needed
to establish whether this title can be packaged.

The reference FFR build uses split release assets and a pinned upstream source.
This build follows that transfer pattern, while using AES-GCM and public standard
runners. Its newer upstream revision requires Xcode 27.2, so it keeps xcode-27
instead of copying the older FFR macos-26 toolchain blindly.
