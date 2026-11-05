# Packaging review, 2026-11-05

The successful local package uses pinned source `cde88f62068e` and shader chain
`b7cd656abd7c`. Upstream main was `56bafa974a18` when checked. Keep a matching
host and shader chain when adopting upstream changes; do not mix new translator
outputs with the already compiled libraries.

| Upstream change | Relevance |
|---|---|
| [Pixel variant fusion](https://github.com/seedds/nxnative/commit/13da1c52e657) | Compiles alpha-test/logic variants together. The author's Pokopia iOS sample fell from 232 to 127 seconds; that is not a BOTW timing guarantee. Requires coordinated chain, ABI, tools and host updates. |
| [Python rewrite scanning](https://github.com/seedds/nxnative/commit/ed3c93ee31fc) | Searches matching text instead of character-by-character rewriting; author's sample was 607 versus 1,426 seconds. Also changes the shader chain. |
| [Archive build caches](https://github.com/seedds/nxnative/commit/fba0096f7d2e) | Stores many cache files in uncompressed tar archives. Useful for the small-file problem; ephemeral GitHub runners still need explicit cache persistence. |
| [Old-chain retention](https://github.com/seedds/nxnative/commit/56bafa974a18) | Reduces stale build storage, rather than speeding a cold compile. |

The current workflow has no cross-run `actions/cache`; a fresh run is a cold
shader build. A future cache should be encrypted, keyed by game, shader chain,
profile inputs and Xcode version, and validated before reuse. This review does
not implement a full chain upgrade or cross-run caching. The current thin IPA
already avoids repeatedly ZIP-packing the full 16 GB of game resources.

Other projects checked:

* [NX2Apple](https://github.com/LNPANDY/NX2Apple) is a GUI frontend sharing the
  nxnative backend. Its separate-data handling is relevant, but it does not
  establish a faster independent BOTW shader compiler. Its
  [release notes](https://github.com/LNPANDY/NX2Apple/releases) also discuss long
  last-worker tails and storage requirements.
* [nxnative-ios](https://github.com/gavin02031/nxnative-ios) is another fork,
  rather than evidence that changing packaging repositories alone fixes slow
  cold translation.
* [BotWRecomp](https://github.com/IshaanKalra2103/BotWRecomp) targets the Wii U
  `U-King.rpx` version with PowerPC recompilation and a CafeOS/Cemu-based runtime.
  Its input format and architecture do not accept this Switch XCI.

The current package contains CoreMotion and standard Switch six-axis input.
Its default-on launcher toggle chooses the device's motion even with a
controller attached. Turning it off restores automatic selection. Real-device
gameplay and the game's SevenSixAxis motion-puzzle paths remain unverified.
