# Touch-only IPA rebuilds

Requested titles: SteamWorld Heist Ultimate Edition 2.2.1, Into the Breach 1.2.88,
Taiko Risshiden V DX 1.1.3, Uncharted Waters IV 1.0.2. Every new package defaults
to op_mode handheld and pad_layout touch, with Info.plist DMTouchOnly=true.

DMTouchOnly is an opt-in UIKit policy. In handheld mode it selects Tap even when
NSUserDefaults remembers an older controller layout. The layout pill is hidden
and its hit test is disabled, so the former top-centre button area reaches the
game. Ordinary packages retain their saved/default layout and layout switch.
Changing the launcher's console mode still explicitly selects its corresponding
input contract; the packaged default is Handheld. No forced env.txt override.

A C policy shared with DmGamepad.m is executed in tests on Windows and macOS.
The initial test failed because saved 2D overrode Tap; the fixed policy passes
saved-layout, handheld/docked and switch visibility cases. A second initial
regression confirmed the compiled/launcher defaults were still Docked; both
now use Handheld. The source overlay is checksum-gated to pinned upstream,
verified idempotent and rejects unknown source versions. The original prepared
module memory regression passes. UIKit compilation and four real package builds
provide integration checks; physical-device touch behavior remains untested.

Existing encrypted compile inputs are reused. After authenticated restoration,
the cloud script applies the explicit input defaults and the reviewed UIKit
source overlay. A small header and two text fragments carry that source through
the existing API transport limit; the joined source SHA256 is verified. No host
or shader translator change. The four standard public free macOS jobs compile
all discovered shaders, run the C input policy test, and verify DMTouchOnly plus
launcher DM_OPMODE=0 in the template before encrypted artifact upload.

The Windows finalizer takes only complete RomFS/aoc entries from each previously
verified IPA, after checking its recorded SHA256. Every other app file comes
from the newly compiled template. This avoids re-extracting large ROMs after the
previous cleanup. It preserves Taiko's verified frame-rate patch/DLC and the
Uncharted module-memory fix. New files use touch-only-unsigned names; old IPAs
remain intact. ZIP CRCs, resource sizes, language, bundle identity, execute mode
and final SHA256 are recorded again. Only these four builds opt into the policy;
therefore regression scope is the input policy, defaults, memory sizing and
four actual app builds, rather than unrelated games or renderer changes.
