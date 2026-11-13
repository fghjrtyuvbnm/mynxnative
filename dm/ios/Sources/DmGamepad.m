// Virtual gamepad (Nintendo button positions) + physical controllers (GameController), handed to the host through dm_input_set and dm_pad_set_player (hle_hid.c, bit layout in dm_input.h).
//   Two layouts, three in handheld mode; one tap on the layout button at the top centre (labelled with the current layout, "2D" / "3D" / "Tap") goes to the next, and the choice is kept in NSUserDefaults (each game is its own app, so per game); the first launch uses the game profile's pad_layout (DM_GAME_PAD_LAYOUT).
//   DMTouchOnly packages select Tap in handheld mode even after a saved controller layout, and hide/disable its layout button.
//   DMTabletPad packages use a 3D layout on iPad with two visible sticks and controls beside the grip; Breath of the Wild 1.9.0 also offers its Action layout.
//   Tap (touch): no control but the layout button in ordinary packages, every other touch goes to the game's touch screen; offered only while the game is in handheld mode, the only one in which it reads the touch screen (Balatro, played by touch).
//   2D (simple): top corners ZL above L (one column), ZR above R likewise, teardrops with the tip toward the screen corner; − and + side by side at the top centre; the left stick in the bottom-left corner (fixed ring, tilt measured from the ring centre, small dead zone);
//     the A (right) B (bottom) X (top) Y (left) diamond in the bottom-right corner, sliding a finger between keys switches keys. Each bottom corner holds a single control, so it sits close in (reaching halfway into the side safe-area inset).
//   3D (full, Pro Controller style): everything in 2D (left stick and diamond keep their place and size), plus a D-pad (inward of and below the left stick, 8-way), a right stick that is not drawn
//     (a touch landing in the right third of the screen on no control holds it: centred where it lands, the centre dragged along once the finger passes the stick radius) and L3 / R3 (small round keys in the top row, inward of ZL / ZR).
//     Breath of the Wild crouches with L3 and uses the scope with R3; 3D World and Breath of the Wild turn the camera with the right stick.
//   Touch-down ownership: locked keys first (shoulders, − / +, the layout button, L3 / R3), then whichever of the diamond, the D-pad and the left stick has the smallest distance / grab radius (the left stick's grab circle borders the D-pad),
//     then in 3D the right stick for a touch in the right third.
//   Everything hugs the edges and corners to leave the picture room; controls sit over the picture, one CAShapeLayer each: a press only swaps the fill, a stick only moves its knob, nothing redraws the whole screen.
//   Touches no control takes (in 3D, those outside the right third) go to the game's touch screen (pushGame; Super Mario Galaxy's pointer in handheld mode).
//   The virtual gamepad (layout button included) hides while a physical controller is connected and comes back when it is removed; meanwhile every touch goes to the game. Physical controllers keep every button (D-pad and right stick included) and map by position: bottom = B, right = A, left = Y, top = X (same positions as on a Switch controller); a Nintendo pad maps by its labels (pad_apple.h).
//   Each physical controller is a player of its own (local co-op), as on the Mac: the first one connected is player 1, together with the touch gamepad, the next player 2, and so on up to 8; see "Physical controllers" below.
//   Shaking the phone shakes the controller (DM_BTN_SHAKE: its six-axis sensor, hle_hid.c), whichever controls are in use; see "Shaking the phone" below.
#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#import <CoreMotion/CoreMotion.h>
#import <CoreText/CoreText.h>
#include <pthread.h>
#include "dm.h"
#include "dm_input.h"
#include "front.h"
#include "game_profile.h"
#include "TouchLayoutPolicy.h"
#include "TabletPadLayout.h"
#include "BotwActionPad.h"
#include "haptics_apple.h"
#include "motion_apple.h"
#include "motion_fusion.h"
#include "pad_apple.h"
#include "pad_slots.h"
#include <stdatomic.h>

enum { C_NONE = 0, C_STICK, C_DPAD, C_FACE, C_BTN, C_SWAP, C_GAME, C_ACTION };
static NSString *const k_botw_layout_key = @"DmBotwPadLayout";

static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static uint64_t g_touch_btn, g_shake_btn;
static int32_t g_touch_lx, g_touch_ly, g_touch_rx, g_touch_ry;
static void publish(void) {   // the touch gamepad and the shake; the host ORs them with player 1's controller and takes whichever stick is deflected more (hle_hid.c)
    pthread_mutex_lock(&g_mu);
    dm_input_set(g_touch_btn | g_shake_btn, g_touch_lx, g_touch_ly, g_touch_rx, g_touch_ry);
    pthread_mutex_unlock(&g_mu);
}

// ---- Shaking the phone ----
// The accelerometer at 60 Hz (no gyroscope, no permission prompt): gravity is followed by a slow low-pass (about 0.8 s), and a sample whose acceleration beyond it exceeds DM_SHAKE_G
// (1.5 G by default; Documents/env.txt overrides) is a hit. The controller is shaken until 120 ms after the last hit: a flick is one shake (the host finishes it as a whole cycle)
// and shaking on keeps it going. Holding the phone and pressing the screen stays far below the threshold. Each detected shake is logged with its peak
static CMMotionManager *g_motion;
static void motion_start(void) {
    if (g_motion) return;
    g_motion = [CMMotionManager new];
    if (!g_motion.accelerometerAvailable) { LOG("front end: no accelerometer, shaking the phone does nothing"); return; }
    const char *e = getenv("DM_SHAKE_G"); double thr = e && atof(e) > 0 ? atof(e) : 1.5;
    LOG("front end: shaking the phone shakes the controller (threshold %.2f G)", thr);
    g_motion.accelerometerUpdateInterval = 1.0 / 60;
    NSOperationQueue *q = [NSOperationQueue new]; q.maxConcurrentOperationCount = 1;
    __block double gx = 0, gy = 0, gz = 0, last = -1, peak = 0; __block BOOL init = NO;
    [g_motion startAccelerometerUpdatesToQueue:q withHandler:^(CMAccelerometerData *d, NSError *err) {
        (void)err; if (!d) return;
        CMAcceleration a = d.acceleration;
        if (!init) { gx = a.x; gy = a.y; gz = a.z; init = YES; }
        double dx = a.x - gx, dy = a.y - gy, dz = a.z - gz, g = sqrt(dx * dx + dy * dy + dz * dz);
        gx += (a.x - gx) * 0.02; gy += (a.y - gy) * 0.02; gz += (a.z - gz) * 0.02;
        if (g > thr) { if (last < 0) peak = 0; last = d.timestamp; peak = fmax(peak, g); }
        BOOL on = last >= 0 && d.timestamp - last < 0.12;
        if (!on && last >= 0) { LOG("front end: phone shaken (peak %.1f G)", peak); last = -1; }
        uint64_t want = on ? DM_BTN_SHAKE : 0;
        pthread_mutex_lock(&g_mu); BOOL changed = g_shake_btn != want; g_shake_btn = want; pthread_mutex_unlock(&g_mu);
        if (changed) publish();
    }];
}

// ---- The phone's gyro ----
// A controller mounted on the phone (Backbone One, Razer Kishi, GameSir G8) has no motion sensors of its own: the phone in the middle is the console, as a Switch in handheld.
// So the phone's device motion (gyro + accelerometer, CoreMotion's fused gravity and user acceleration, 100 Hz, no permission prompt) drives player 1's six-axis sensor, turned
// into the Switch frame for the screen's orientation (motion_phone_to_switch, motion_fusion.h): x to the right of the picture, y to its top, z toward the player.
// The host keeps phone and controller orientations separately, choosing fresh controller data in auto mode and the phone alone in forced mode.
// DM_PHONE_MOTION: auto (default) while no controller supplies fresh gyro data (a DualSense held apart from the phone uses its own, motion_apple.h), 1 always, 0 never.
// DM_MOTION=0 (all live motion off; the NSP script's --no-motion builds it in) never starts device motion.
// Which frame the samples come in: on iOS 27 and later the pad view (full screen, over the picture) is the motion body (CMMotionManager.deviceMotionBody), so Core Motion delivers
// them in that view's frame for whichever display shows it and however it is turned: x to the right of the picture, y to its top, z toward the player, the Switch frame as it is.
// Before that they come in the hardware frame, turned here by the interface orientation, which holds only where the hardware frame is the screen's portrait frame: not on iPhone
// Duo's inner display, whose picture is a quarter turn from it (up / down and left / right swapped, GitHub issue #569). Open: while the scene is not full screen (Split View on the
// inner display) Core Motion falls back to the hardware frame without saying so, and the samples are then taken as the view's frame
static _Atomic int g_iface_orient = 3;      // UIInterfaceOrientation, updated on layout
static BOOL g_motion_body;                  // samples in the body's frame (iOS 27+)
static void phone_motion_start(UIView *body) {
    const char *e = getenv("DM_MOTION");
    if (e && !atoi(e)) { LOG("front end: motion is off (DM_MOTION=0), the phone's gyro is not used"); return; }
    e = getenv("DM_PHONE_MOTION"); int mode = !e || !strcmp(e, "auto") ? -1 : atoi(e);
    if (!mode) { LOG("front end: the phone's gyro is off (DM_PHONE_MOTION=0)"); return; }
    if (!g_motion.deviceMotionAvailable) { LOG("front end: no device motion, the phone's gyro is not used"); return; }
    LOG("front end: the phone's gyro drives the controller's six-axis sensor %s", mode < 0 ? "while no controller supplies fresh motion" : "always (DM_PHONE_MOTION=1)");
    g_motion.deviceMotionUpdateInterval = 1.0 / 100;
    if (@available(iOS 27.0, *)) { g_motion.deviceMotionBody = body; g_motion_body = YES; LOG("front end: the phone's motion comes in the pad view's frame (deviceMotionBody)"); }
    NSOperationQueue *q = [NSOperationQueue new]; q.maxConcurrentOperationCount = 1;
    [g_motion startDeviceMotionUpdatesToQueue:q withHandler:^(CMDeviceMotion *d, NSError *err) {
        (void)err; if (!d) return;
        float a[3] = {(float)(d.gravity.x + d.userAcceleration.x), (float)(d.gravity.y + d.userAcceleration.y), (float)(d.gravity.z + d.userAcceleration.z)};
        float w[3] = {(float)d.rotationRate.x, (float)d.rotationRate.y, (float)d.rotationRate.z}, as[3], ws[3];
        int o = g_motion_body ? 1 : atomic_load(&g_iface_orient);   // the body's frame is already the picture's: the portrait map, which leaves it as it is
        motion_phone_to_switch(o, a, as); motion_phone_to_switch(o, w, ws);
        dm_motion_set_switch(0, as, ws);
    }];
}

// ---- Layout constants (in u; x measured from the outer edge, the right half mirrors) ----
static const CGFloat
    K_ZL_X = 44, K_ZL_Y = 40, K_ZL_R = 26,          // ZL / ZR: centre from the outer edge and the top, radius
    K_L_X = 44, K_L_Y = 108, K_L_R = 24,            // L / R: same column as ZL / ZR
    K_DROP_TIP = 1.45,                              // teardrop tip distance from the centre (times the radius)
    K_CORNER_IN = 0.5,                              // how far the bottom-corner controls reach into the side safe-area inset (in landscape there is only the rounded screen corner there; the Dynamic Island is mid-edge)
    K_FACE_X = 81, K_PAD_Y = 82,                    // diamond centre from the outer edge; diamond and stick centre from the bottom (B's lower edge about 5 above it)
    K_FACE_GAP = 50, K_FACE_R = 27,                 // diamond: key distance from the centre, key radius
    K_PILL_DX = 52, K_PILL_Y = 22, K_PILL_W = 50, K_PILL_H = 28,   // − / +: centre from the screen's midline (the middle goes to the layout button) and from the top, size
    K_SWAP_R = 15,                                  // layout button: top centre, level with − / +
    K_STICK_X = 81, K_STICK_R = 77, K_KNOB_R = 30,  // left stick: mirrors the diamond, the ring as large as the whole diamond (key distance + key radius), the knob a little larger than a diamond key
    K_STICK_GRAB = 1.4,                             // how near the ring centre a touch-down grabs a stick (times the ring radius)
    K_FULL = 0.8,                                   // full tilt at this fraction of the ring radius (the knob still travels to the ring edge)
    K_DEAD = 0.1,                                   // stick dead zone (times the ring radius)
    // controls only the 3D layout has
    K_LOW_X = 231, K_LOW_Y = 64,                    // D-pad centre from the outer edge and the bottom (inward of and below the left stick, as on a Pro Controller)
    K_DPAD_R = 48, K_ARM_W = 17, K_ARM_IN = 11,     // D-pad: arm outer edge from the centre, half-width, tip from the centre
    K_DPAD_GRAB = 1.3,                              // D-pad grab radius (times the outer edge)
    K_RSTICK_R = 60,                                // right stick (not drawn): radius around its centre, the touch-down point
    K_RSWIPE = 1.0 / 3,                             // right stick area: this fraction of the screen width from the right edge (not in u)
    K_CLICK_X = 102, K_CLICK_R = 17;                // L3 / R3: centre from the outer edge (level with ZL / ZR), radius
static const int k_btns[] = {B_ZL, B_L, B_ZR, B_R, B_MINUS, B_PLUS, B_LS, B_RS};   // keys locked at touch-down (L3 / R3 only in the 3D layout)
static const int k_tabletDirections[DM_TABLET_DIRECTIONS] = {B_UP, B_RIGHT, B_DOWN, B_LEFT};
static NSString *const k_layout_key = @"DmPadLayout";   // NSUserDefaults: 0 = 2D, 1 = 3D, 2 = Tap (DM_GAME_PAD_LAYOUT's numbers)
int dm_opmode(void);   // hle_oe.c: 0 = handheld

@interface DmGamepad : UIView
- (instancetype)initWithFrame:(CGRect)frame preview:(BOOL)preview;
- (void)setTabletSize:(double)size lift:(double)lift;
@end
static __weak DmGamepad *g_view;
static void pads_start(void);   // Physical controllers, below

@implementation DmGamepad {
    NSMapTable<UITouch *, NSNumber *> *_owner;     // touch → control (with the key for C_BTN or the stick for C_STICK, << 8)
    UITouch *_stick[2]; CGPoint _stickNow[2];      // the touch holding each stick and where it is now (0 left, 1 right)
    CGPoint _floatingCentre[2];                    // where each floating stick landed, dragged along past its radius
    CGPoint _stickTouchOffset[2];                 // edge touches can start outside the centre's travel limits
    uint64_t _faceBits, _dpadBits, _btnBits;
    NSMapTable<UITouch *, NSNumber *> *_faceOf;    // which keys each touch on the diamond currently holds
    CAShapeLayer *_key[B_N]; CATextLayer *_label[B_N];   // one layer per key
    CAShapeLayer *_ring, *_knob, *_rightRing, *_rightKnob;
    CAShapeLayer *_swap; CATextLayer *_swapLabel; BOOL _swapHeld;
    UIImpactFeedbackGenerator *_touchFeedback;       // one short feedback per touch-control press edge
    unsigned _hapticSticks;
    BOOL _stickShown;                              // a visible stick was held at the last refresh
    BOOL _tabletPad;                               // this package opts into the iPad layout
    BOOL _hasActionPad, _actionPad;
    DmActionInput _actionInput;
    uint64_t _actionHeld;
    CAShapeLayer *_actionKey[DM_ACTION_COUNT], *_actionBadge[DM_ACTION_COUNT];
    CALayer *_actionIcon[DM_ACTION_COUNT];
    CATextLayer *_actionLabel[DM_ACTION_COUNT], *_actionCycle[3];
    BOOL _preview;
    double _tabletSize, _tabletLift;
    BOOL _touchOnly;                              // explicit touch-only package policy
    BOOL _full, _tap;                              // the 3D layout / the Tap layout is current
    CALayer *_controls;                            // holds every control layer: hidden while a physical controller is connected (the view itself stays, for game touches)
    BOOL _padOff;                                  // a physical controller is connected: every touch goes to the game
    UITouch *_game[16];                            // touches on the game's touch screen by finger slot
}

static UIColor *k_idle, *k_on, *k_line, *k_ringFill, *k_text, *k_textOn;
static CAShapeLayer *shape(CALayer *parent) {
    CAShapeLayer *l = [CAShapeLayer layer];
    l.fillColor = k_idle.CGColor; l.strokeColor = k_line.CGColor; l.lineWidth = 1.5;
    l.shadowColor = UIColor.blackColor.CGColor; l.shadowOpacity = 0.2; l.shadowRadius = 3; l.shadowOffset = CGSizeMake(0, 1);
    [parent addSublayer:l]; return l;
}
static CATextLayer *label(CALayer *parent, NSString *s) {
    CATextLayer *t = [CATextLayer layer];
    t.string = s; t.alignmentMode = kCAAlignmentCenter; t.foregroundColor = k_text.CGColor; t.contentsScale = UIScreen.mainScreen.scale;
    [parent addSublayer:t]; return t;
}
static BOOL fullOnly(int b) { return b == B_LS || b == B_RS || b >= B_LEFT; }   // keys shown only in the 3D layout
static UIImage *actionIcon(NSString *name) {
    if ([name isEqualToString:@"bow"]) {
        return [[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(38, 38)] imageWithActions:^(UIGraphicsImageRendererContext *ctx) {
            (void)ctx;
            UIBezierPath *p = [UIBezierPath bezierPath];
            [p moveToPoint:CGPointMake(7, 12)];
            [p addQuadCurveToPoint:CGPointMake(26, 31) controlPoint:CGPointMake(31, 7)];
            [p addLineToPoint:CGPointMake(11, 27)]; [p addLineToPoint:CGPointMake(7, 12)];
            [p moveToPoint:CGPointMake(8, 30)]; [p addLineToPoint:CGPointMake(31, 7)];
            [p moveToPoint:CGPointMake(24, 8)]; [p addLineToPoint:CGPointMake(31, 7)];
            [p addLineToPoint:CGPointMake(30, 14)];
            [UIColor.whiteColor setStroke]; p.lineWidth = 2.2; p.lineCapStyle = kCGLineCapRound; p.lineJoinStyle = kCGLineJoinRound; [p stroke];
        }];
    }
    UIImage *symbol = [UIImage systemImageNamed:name withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:27 weight:UIImageSymbolWeightSemibold]];
    if (!symbol) return nil;
    symbol = [symbol imageWithTintColor:UIColor.whiteColor renderingMode:UIImageRenderingModeAlwaysOriginal];
    return [[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(38, 38)] imageWithActions:^(UIGraphicsImageRendererContext *ctx) {
        (void)ctx;
        CGFloat s = MIN(29 / symbol.size.width, 29 / symbol.size.height);
        CGSize sz = CGSizeMake(symbol.size.width * s, symbol.size.height * s);
        [symbol drawInRect:CGRectMake((38 - sz.width) / 2, (38 - sz.height) / 2, sz.width, sz.height)];
    }];
}

- (instancetype)initWithFrame:(CGRect)f preview:(BOOL)preview {
    if ((self = [super initWithFrame:f])) {
        self.multipleTouchEnabled = YES; self.opaque = NO; self.backgroundColor = UIColor.clearColor;
        const char *feedback = getenv("DM_TOUCH_HAPTICS");
        if (!preview && (!feedback || atoi(feedback))) {
            _touchFeedback = [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleLight];
            [_touchFeedback prepare];
        }
        _owner = [NSMapTable strongToStrongObjectsMapTable]; _faceOf = [NSMapTable strongToStrongObjectsMapTable];
        static dispatch_once_t once;
        dispatch_once(&once, ^{
            // each colour carries its own low opacity instead of lowering the whole view's alpha (that would add an off-screen pass for the full-screen layer)
            k_idle = [UIColor colorWithWhite:1 alpha:0.14]; k_on = [UIColor colorWithWhite:1 alpha:0.45]; k_line = [UIColor colorWithWhite:1 alpha:0.38];
            k_ringFill = [UIColor colorWithWhite:1 alpha:0.06]; k_text = [UIColor colorWithWhite:1 alpha:0.6]; k_textOn = [UIColor colorWithWhite:0 alpha:0.7];
        });
        _controls = [CALayer layer]; [self.layer addSublayer:_controls];
        _ring = shape(_controls); _ring.fillColor = k_ringFill.CGColor;
        _knob = shape(_controls);
        _preview = preview;
        self.userInteractionEnabled = !preview;
        _tabletPad = preview || (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad &&
                                 [NSBundle.mainBundle.infoDictionary[@"DMTabletPad"] boolValue]);
        _hasActionPad = !preview && _tabletPad &&
            [NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.nxnative.01007ef00011e000.v190"];
        _actionPad = _hasActionPad && [NSUserDefaults.standardUserDefaults boolForKey:k_botw_layout_key];
        const char *size = getenv("DM_TABLET_PAD_SIZE"), *lift = getenv("DM_TABLET_PAD_LIFT");
        _tabletSize = !preview && size ? atof(size) : 100;
        _tabletLift = !preview && lift ? atof(lift) : 0;
        if (_tabletPad) {
            _rightRing = shape(_controls);
            _rightRing.fillColor = k_ringFill.CGColor;
            _rightKnob = shape(_controls);
        }
        CAShapeLayer *in = [CAShapeLayer layer]; in.fillColor = nil; in.strokeColor = k_line.CGColor; in.lineWidth = 1.5;   // inner ring of the knob
        [_knob addSublayer:in];
        static NSString *const names[B_N] = {@"A", @"B", @"X", @"Y", @"L3", @"R3", @"L", @"R", @"ZL", @"ZR", @"+", @"−"};
        for (int b = 0; b < B_N; b++) {
            _key[b] = shape(_controls);
            if (names[b]) _label[b] = label(_key[b], names[b]);
        }
        if (_tabletPad) {
            static NSString *const arrows[DM_TABLET_DIRECTIONS] = {@"↑", @"→", @"↓", @"←"};
            for (int i = 0; i < DM_TABLET_DIRECTIONS; i++) {
                int b = k_tabletDirections[i];
                _label[b] = label(_key[b], arrows[i]);
            }
        }
        if (_hasActionPad) {
            static NSString *const icons[DM_ACTION_COUNT] = {
                @"sword", @"shield", @"eye", @"shield", @"eye", @"lock.fill", @"xmark",
                @"map", @"figure.cooldown", @"bow", @"sword", @"figure.jumprope",
                @"hand.raised.fill", @"figure.run", @"backpack.fill", @"scope", @"arrow.up.right.circle", @"speaker.wave.2",
            };
            static NSString *const fallback[DM_ACTION_COUNT] = {
                @"⚔", @"◇", @"◉", @"◇", @"◉", @"▣", @"×", @"▤", @"⌄",
                @"🏹", @"⚔", @"↟", @"✋", @"»", @"▣", @"⊙", @"↗", @"♪",
            };
            static NSString *const badges[B_N] = {
                @"A", @"B", @"X", @"Y", @"L3", @"R3", @"L", @"R", @"ZL", @"ZR", @"+", @"−", @"←", @"↑", @"→", @"↓",
            };
            for (int i = 0; i < DM_ACTION_COUNT; i++) {
                _actionKey[i] = shape(_controls);
                UIImage *icon = actionIcon(icons[i]);
                if (icon) {
                    _actionIcon[i] = [CALayer layer]; _actionIcon[i].contents = (__bridge id)icon.CGImage;
                    [_actionKey[i] addSublayer:_actionIcon[i]];
                } else _actionIcon[i] = label(_actionKey[i], fallback[i]);
                if (i < 3) _actionCycle[i] = label(_actionKey[i], @"↻");
                _actionBadge[i] = shape(_actionKey[i]);
                _actionBadge[i].fillColor = [UIColor colorWithWhite:0.12 alpha:0.93].CGColor;
                _actionLabel[i] = label(_actionBadge[i], badges[dm_action_buttons[i].button]);
            }
        }
        _swap = shape(_controls); _swapLabel = label(_swap, @"");
        if (preview) {
            _full = YES;
            [self applyLayout];
            return self;
        }
        NSNumber *saved = [NSUserDefaults.standardUserDefaults objectForKey:k_layout_key];
        _touchOnly = [NSBundle.mainBundle.infoDictionary[@"DMTouchOnly"] boolValue];
        int l = dm_initial_pad_layout(DM_GAME_PAD_LAYOUT, (int)saved.integerValue, saved != nil, dm_opmode() == 0, _touchOnly);
        if (l == 2 && dm_opmode() != 0) l = 0;   // Tap only in handheld mode (env.txt's DM_OPMODE may have changed it)
        _full = _tabletPad || l == 1; _tap = !_tabletPad && l == 2;
        [self applyLayout];
        NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
        [nc addObserver:self selector:@selector(padsChanged:) name:GCControllerDidConnectNotification object:nil];
        [nc addObserver:self selector:@selector(padsChanged:) name:GCControllerDidDisconnectNotification object:nil];
        pads_start();
        [self padsChanged:nil];
        motion_start();
        phone_motion_start(self);
    }
    return self;
}
- (void)applyLayout {   // show / hide the controls for the current layout
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    for (int b = 0; b < B_N; b++) _key[b].hidden = _actionPad || _tap || (fullOnly(b) && !_full);
    for (int i = 0; i < DM_ACTION_COUNT; i++) _actionKey[i].hidden = !_actionPad;
    _ring.hidden = _knob.hidden = _tap;
    _swap.hidden = !_hasActionPad && (_tabletPad || !dm_layout_switch_visible(_tap, _touchOnly));
    _swapLabel.string = _actionPad ? @"Action" : _tap ? @"Tap" : _full ? @"3D" : @"2D";
    [CATransaction commit];
}
- (void)nextLayout {   // 2D → 3D (→ Tap in handheld mode) → 2D: release every touch first (no key stays held), save, lay out again
    int l = _tap ? 0 : _full ? (dm_opmode() == 0 ? 2 : 0) : 1;
    [self reset];
    if (_hasActionPad) {
        _actionPad = !_actionPad;
        [NSUserDefaults.standardUserDefaults setBool:_actionPad forKey:k_botw_layout_key];
    } else {
        _full = l == 1; _tap = l == 2;
        [NSUserDefaults.standardUserDefaults setObject:@(l) forKey:k_layout_key];
    }
    [self applyLayout]; [self setNeedsLayout];
}

// ---- Layout (points; computed inside the safe area) ----
- (CGRect)safe { return _preview ? self.bounds : UIEdgeInsetsInsetRect(self.bounds, self.safeAreaInsets); }
- (CGRect)corner { UIEdgeInsets i = self.safeAreaInsets; i.left *= K_CORNER_IN; i.right *= K_CORNER_IN; return UIEdgeInsetsInsetRect(self.bounds, i); }   // the rectangle the bottom-corner controls use
- (void)setTabletSize:(double)size lift:(double)lift {
    if (size == _tabletSize && lift == _tabletLift) return;
    _tabletSize = size;
    _tabletLift = lift;
    [self setNeedsLayout];
}
- (DmTabletMetrics)tabletMetrics:(CGRect)s {
    return dm_tablet_pad_metrics(s.size.width, s.size.height, _tabletSize, _tabletLift);
}
- (CGFloat)u {
    return _tabletPad ? [self tabletMetrics:self.safe].scale : MIN(self.bounds.size.height / 430.0, 1.3);
}
static CGPoint side(CGRect s, int right, CGFloat dx, CGFloat y) { return CGPointMake(right ? CGRectGetMaxX(s) - dx : CGRectGetMinX(s) + dx, y); }
- (CGFloat)actionScale { CGRect s = self.safe; return dm_action_scale(s.size.width, s.size.height); }
- (CGPoint)actionPoint:(BOOL)right x:(CGFloat)x y:(CGFloat)y {
    CGRect s = self.safe; CGFloat scale = self.actionScale;
    return side(s, right, x * scale, CGRectGetMidY(s) + y * scale);
}
- (CGPoint)actionLocal:(CGPoint)p right:(BOOL)right {
    CGRect s = self.safe; CGFloat scale = self.actionScale;
    if (scale <= 0) return CGPointMake(-1e6, -1e6);
    return CGPointMake((right ? CGRectGetMaxX(s) - p.x : p.x - CGRectGetMinX(s)) / scale,
                       (p.y - CGRectGetMidY(s)) / scale);
}
- (CGPoint)clampTabletStick:(CGPoint)p right:(BOOL)right {
    if (_actionPad) {
        CGPoint local = [self actionLocal:p right:right];
        double x = local.x, y = local.y;
        dm_action_stick_clamp(right, &x, &y);
        return [self actionPoint:right x:x y:y];
    }
    CGPoint local = [self tabletLocal:p right:right];
    double x = local.x, y = local.y;
    dm_tablet_stick_clamp(&x, &y);
    return [self tabletPoint:right x:x y:y];
}
- (CGPoint)tabletPoint:(BOOL)right x:(CGFloat)x y:(CGFloat)y {
    CGRect s = self.safe;
    DmTabletMetrics m = [self tabletMetrics:s];
    return side(s, right, x * m.scale, CGRectGetMaxY(s) - dm_tablet_pad_y(m, y));
}
- (CGPoint)tabletLocal:(CGPoint)p right:(BOOL)right {
    CGRect s = self.safe;
    DmTabletMetrics m = [self tabletMetrics:s];
    CGFloat x = right ? CGRectGetMaxX(s) - p.x : p.x - CGRectGetMinX(s);
    return CGPointMake(x / m.scale, (CGRectGetMaxY(s) - p.y - m.centre) / m.scale);
}
- (CGPoint)faceCenter {
    if (_tabletPad) return [self tabletPoint:YES x:DM_TABLET_FACE_X y:DM_TABLET_FACE_Y];
    CGRect s = self.corner; CGFloat u = self.u; return side(s, 1, K_FACE_X * u, CGRectGetMaxY(s) - K_PAD_Y * u);
}
- (CGFloat)faceGap { return (_tabletPad ? DM_TABLET_FACE_GAP : K_FACE_GAP) * self.u; }
- (CGFloat)faceR { return (_tabletPad ? DM_TABLET_FACE_R : K_FACE_R) * self.u; }
- (CGPoint)facePos:(int)b { CGPoint c = self.faceCenter; CGFloat g = self.faceGap;
    switch (b) { case B_A: return CGPointMake(c.x + g, c.y); case B_B: return CGPointMake(c.x, c.y + g); case B_X: return CGPointMake(c.x, c.y - g); default: return CGPointMake(c.x - g, c.y); } }
- (CGPoint)stickCentre:(int)i {
    if (_actionPad) return _stick[i] ? _floatingCentre[i] : [self actionPoint:i != 0 x:dm_action_stick_x(i) y:0];
    if (_tabletPad) return _stick[i] ? _floatingCentre[i] : [self tabletPoint:i != 0 x:DM_TABLET_STICK_X y:DM_TABLET_STICK_Y];
    if (i) return _floatingCentre[i];
    CGRect s = self.corner;
    return side(s, 0, K_STICK_X * self.u, CGRectGetMaxY(s) - K_PAD_Y * self.u);
}
- (CGFloat)stickR:(int)i { return _actionPad ? DM_ACTION_STICK_R * self.actionScale : (_tabletPad ? DM_TABLET_STICK_R : i ? K_RSTICK_R : K_STICK_R) * self.u; }
- (BOOL)inRightArea:(CGPoint)p { CGRect b = self.bounds; return p.x >= CGRectGetMaxX(b) - b.size.width * K_RSWIPE; }
- (CGPoint)dpadCenter {
    if (_tabletPad) return [self tabletPoint:NO x:DM_TABLET_FACE_X y:DM_TABLET_FACE_Y];
    CGRect s = self.corner; CGFloat u = self.u; return side(s, 0, K_LOW_X * u, CGRectGetMaxY(s) - K_LOW_Y * u);
}
- (CGFloat)dpadR { return K_DPAD_R * self.u; }
static BOOL isDrop(int b) { return b == B_ZL || b == B_L || b == B_ZR || b == B_R; }
static BOOL isClick(int b) { return b == B_LS || b == B_RS; }
- (CGPoint)dropCenter:(int)b { CGRect s = self.safe; CGFloat u = self.u; BOOL z = b == B_ZL || b == B_ZR;
    if (_tabletPad) return [self tabletPoint:b == B_ZR || b == B_R x:z ? DM_TABLET_SHOULDER_OUT_X : DM_TABLET_SHOULDER_IN_X y:DM_TABLET_SHOULDER_Y];
    return side(s, b == B_ZR || b == B_R, (z ? K_ZL_X : K_L_X) * u, CGRectGetMinY(s) + (z ? K_ZL_Y : K_L_Y) * u); }
- (CGFloat)dropR:(int)b { return (_tabletPad ? DM_TABLET_SHOULDER_R : b == B_ZL || b == B_ZR ? K_ZL_R : K_L_R) * self.u; }
- (CGFloat)clickR { return (_tabletPad ? DM_TABLET_CLICK_R : K_CLICK_R) * self.u; }
- (CGPoint)clickCenter:(int)b {
    if (_tabletPad) return [self tabletPoint:b == B_RS x:DM_TABLET_CLICK_X y:DM_TABLET_STICK_Y];
    CGRect s = self.safe; CGFloat u = self.u; return side(s, b == B_RS, K_CLICK_X * u, CGRectGetMinY(s) + K_ZL_Y * u);
}
- (CGRect)pillRect:(int)b { CGRect s = self.safe; CGFloat u = self.u, w = K_PILL_W * u, h = K_PILL_H * u;
    CGPoint c = CGPointMake(CGRectGetMidX(s) + (b == B_PLUS ? K_PILL_DX : -K_PILL_DX) * u, CGRectGetMinY(s) + K_PILL_Y * u);   // − on the left, + on the right
    if (_tabletPad) {
        c = [self tabletPoint:b == B_PLUS x:DM_TABLET_MENU_X y:DM_TABLET_MENU_Y];
        w = DM_TABLET_MENU_W * u; h = DM_TABLET_MENU_H * u;
    }
    return CGRectMake(c.x - w / 2, c.y - h / 2, w, h); }
- (CGPoint)swapCenter { CGRect s = self.safe; return CGPointMake(CGRectGetMidX(s), CGRectGetMinY(s) + (_hasActionPad ? 25 : K_PILL_Y * self.u)); }

static CGFloat dist(CGPoint a, CGPoint b) { return hypot(a.x - b.x, a.y - b.y); }
- (int)btnAt:(CGPoint)p {   // locked keys (tested on touch-down only, then locked)
    CGFloat u = self.u;
    for (int i = 0; i < (int)(sizeof k_btns / sizeof *k_btns); i++) { int b = k_btns[i];
        if (fullOnly(b) && !_full) continue;
        BOOL hit = isDrop(b) ? dist(p, [self dropCenter:b]) <= [self dropR:b] * 1.35
                 : isClick(b) ? dist(p, [self clickCenter:b]) <= self.clickR * 1.35
                 : CGRectContainsPoint(CGRectInset([self pillRect:b], -8 * u, -8 * u), p);
        if (hit) return b; }
    return -1;
}
- (BOOL)inSwap:(CGPoint)p {
    if (_hasActionPad) {
        CGPoint c = self.swapCenter;
        return fabs(p.x - c.x) <= 28 && fabs(p.y - c.y) <= 22;
    }
    return !_tabletPad && dm_layout_switch_visible(_tap, _touchOnly) && dist(p, self.swapCenter) <= K_SWAP_R * self.u * 1.6;
}
- (uint64_t)faceAt:(CGPoint)p {   // keys under the finger in the diamond (between two keys both count)
    uint64_t m = 0; CGFloat r = self.faceR * 1.25;
    for (int b = B_A; b <= B_Y; b++) if (dist(p, [self facePos:b]) <= r) m |= 1ull << b;
    return m;
}
- (uint64_t)dpadAt:(CGPoint)p {   // 8 directions: 45° each, diagonals press two keys; a small centre circle counts as none
    CGPoint c = self.dpadCenter; CGFloat dx = p.x - c.x, dy = p.y - c.y;
    if (_tabletPad) {
        CGFloat u = self.u;
        if (u <= 0) return 0;
        unsigned directions = dm_tablet_dpad_at(dx / u, dy / u);
        uint64_t mask = 0;
        for (int i = 0; i < DM_TABLET_DIRECTIONS; i++)
            if (directions & (1u << i)) mask |= 1ull << k_tabletDirections[i];
        return mask;
    }
    if (hypot(dx, dy) < self.dpadR * 0.25) return 0;
    double a = atan2(-dy, dx) * 180 / M_PI; uint64_t m = 0;
    if (a > -67.5 && a < 67.5) m |= 1ull << B_RIGHT;
    if (a > 22.5 && a < 157.5) m |= 1ull << B_UP;
    if (a > 112.5 || a < -112.5) m |= 1ull << B_LEFT;
    if (a < -22.5 && a > -157.5) m |= 1ull << B_DOWN;
    return m;
}
- (CGPoint)knobOffset:(int)i {   // knob offset from the stick centre (clamped to the stick radius)
    if (!_stick[i]) return CGPointZero;
    CGPoint h = [self stickCentre:i]; CGFloat dx = _stickNow[i].x - h.x, dy = _stickNow[i].y - h.y, d = hypot(dx, dy), R = [self stickR:i];
    if (d > R) { dx *= R / d; dy *= R / d; }
    return CGPointMake(dx, dy);
}

// ---- Touch ----
- (void)recompute {
    uint64_t face = 0; for (UITouch *t in _faceOf) face |= [_faceOf objectForKey:t].unsignedLongLongValue;
    uint64_t btn = 0, dpad = 0, action = 0; BOOL swap = NO;
    for (UITouch *t in _owner) { uint64_t v = [_owner objectForKey:t].unsignedLongLongValue; int c = (int)(v & 0xff);
        if (c == C_BTN) btn |= 1ull << (v >> 8);
        else if (c == C_DPAD) dpad |= [self dpadAt:[t locationInView:self]];
        else if (c == C_SWAP) swap = YES;
        else if (c == C_ACTION) {
            int i = (int)(v >> 8);
            if (i > DM_ACTION_RUNE_MENU && i != DM_ACTION_LOCK) {
                btn |= UINT64_C(1) << dm_action_buttons[i].button;
                action |= UINT64_C(1) << i;
            }
        }
    }
    if (_actionPad) btn |= dm_action_bits(_actionInput);
    int32_t ax[4] = {0};
    for (int i = 0; i < 2; i++) {
        CGPoint o = [self knobOffset:i]; CGFloat R = [self stickR:i], d = hypot(o.x, o.y), dz = R * K_DEAD;
        if (d <= dz) continue;
        CGFloat m = fmin((d - dz) / (R * K_FULL - dz), 1) / d;   // outside the dead zone: 0 rising to full at the full-tilt radius
        ax[i * 2] = (int32_t)lrint(o.x * m * 32767); ax[i * 2 + 1] = (int32_t)lrint(-o.y * m * 32767);   // host: up is positive; rounded so full tilt is exactly 32767
    }
    if (_actionPad) dm_action_route_sticks(_actionInput, ax);
    BOOL changed = face != _faceBits || dpad != _dpadBits || btn != _btnBits || swap != _swapHeld || action != _actionHeld;
    uint64_t pressed = (face | dpad | btn) & ~(_faceBits | _dpadBits | _btnBits);
    unsigned gripping = (_stick[0] ? 1u : 0) | (_stick[1] ? 2u : 0);
    if (pressed || (swap && !_swapHeld) || (gripping & ~_hapticSticks)) {
        [_touchFeedback impactOccurredWithIntensity:0.6]; [_touchFeedback prepare];
    }
    _hapticSticks = gripping;
    _faceBits = face; _dpadBits = dpad; _btnBits = btn; _swapHeld = swap; _actionHeld = action;
    pthread_mutex_lock(&g_mu);
    g_touch_btn = face | dpad | btn; g_touch_lx = ax[0]; g_touch_ly = ax[1]; g_touch_rx = ax[2]; g_touch_ry = ax[3];
    pthread_mutex_unlock(&g_mu);
    publish();
    BOOL stick = _stick[0] != nil || (_tabletPad && _stick[1] != nil);
    if (changed || stick || _stickShown) [self refresh];   // also refresh on the stick release so the knob returns to the centre
    _stickShown = stick;
}
// Touches no control takes (all of them while a physical controller is connected) go to the game's touch screen, normalized on the 16:9 picture that front_ios.m
// centres in the screen: Super Mario Galaxy's pointer in handheld mode (profile op_mode). The host reports them only in handheld mode, as on the Switch (hle_hid.c touch_read)
- (void)pushGame {
    CGRect b = self.bounds; CGFloat w = b.size.width, h = b.size.height;
    if (w <= 0 || h <= 0) return;
    if (w / h > 16.0 / 9.0) w = h * 16.0 / 9.0; else h = w * 9.0 / 16.0;
    CGFloat x0 = (b.size.width - w) / 2, y0 = (b.size.height - h) / 2;
    dm_touch t[16]; int n = 0;
    for (int i = 0; i < 16; i++) if (_game[i]) {
        CGPoint p = [_game[i] locationInView:self];
        t[n++] = (dm_touch){(uint32_t)i, (float)fmin(fmax((p.x - x0) / w, 0), 0.999), (float)fmin(fmax((p.y - y0) / h, 0), 0.999)};
    }
    dm_touch_set(t, n);
}
- (BOOL)gameBegin:(UITouch *)t {
    for (int i = 0; i < 16; i++) if (!_game[i]) { _game[i] = t; [_owner setObject:@(C_GAME | (uint64_t)i << 8) forKey:t]; return YES; }
    return NO;
}
- (void)touchesBegan:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e {
    BOOL game = NO;
    for (UITouch *t in ts) {
        if (_padOff) { game |= [self gameBegin:t]; continue; }
        CGPoint p = [t locationInView:self];
        int idx = p.x >= CGRectGetMidX(self.safe);
        CGPoint local = _actionPad ? [self actionLocal:p right:idx != 0] : CGPointZero;
        int action = _actionPad ? dm_action_hit(idx, local.x, local.y) : -1;
        if (action >= 0) { [_owner setObject:@(C_ACTION | (uint64_t)action << 8) forKey:t]; continue; }
        int hit = (_tap || _actionPad) ? -1 : [self btnAt:p];
        if (hit >= 0) { [_owner setObject:@(C_BTN | (uint64_t)hit << 8) forKey:t]; continue; }
        if ([self inSwap:p]) { [_owner setObject:@(C_SWAP) forKey:t]; continue; }
        if (_tap) { game |= [self gameBegin:t]; continue; }
        // diamond, D-pad, left stick: take the one with the smallest distance / grab radius, if it is <= 1
        CGFloat best = 1; int kind = C_NONE;
        if (_actionPad) {
            if (!_stick[idx] && dm_action_stick_contains(idx, local.x, local.y)) kind = C_STICK;
        } else {
            CGFloat f = dist(p, self.faceCenter) / (self.faceGap + self.faceR * 1.6); if (f <= best) { best = f; kind = C_FACE; }
            if (_tabletPad) {
                if ([self dpadAt:p]) kind = C_DPAD;
            } else if (_full) {
                CGFloat d = dist(p, self.dpadCenter) / (self.dpadR * K_DPAD_GRAB);
                if (d < best) { best = d; kind = C_DPAD; }
            }
            if (_tabletPad && kind == C_NONE && self.u > 0) {
                CGPoint tablet = [self tabletLocal:p right:idx != 0];
                if (!_stick[idx] && dm_tablet_stick_contains(tablet.x, tablet.y)) kind = C_STICK;
            }
        }
        if (!_tabletPad && !_stick[0] && dist(p, [self stickCentre:0]) < best * [self stickR:0] * K_STICK_GRAB) { kind = C_STICK; idx = 0; }
        if (!_tabletPad && kind == C_NONE && _full && !_stick[1] && [self inRightArea:p]) { kind = C_STICK; idx = 1; }
        if (kind == C_FACE) { [_owner setObject:@(C_FACE) forKey:t]; [_faceOf setObject:@([self faceAt:p]) forKey:t]; }
        else if (kind == C_DPAD) [_owner setObject:@(C_DPAD) forKey:t];
        else if (kind == C_STICK) {
            [_owner setObject:@(C_STICK | (uint64_t)idx << 8) forKey:t];
            CGPoint centre = p;
            if (_tabletPad) centre = [self clampTabletStick:p right:idx != 0];
            _stickTouchOffset[idx] = CGPointMake(centre.x - p.x, centre.y - p.y);
            _stick[idx] = t; _stickNow[idx] = _floatingCentre[idx] = centre;
        }
        else game |= [self gameBegin:t];
    }
    if (game) [self pushGame];
    [self recompute];
}
- (void)touchesMoved:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e {
    BOOL game = NO;
    for (UITouch *t in ts) {
        uint64_t v = [_owner objectForKey:t].unsignedLongLongValue; int c = (int)(v & 0xff); CGPoint p = [t locationInView:self];
        if (c == C_FACE) [_faceOf setObject:@([self faceAt:p]) forKey:t];
        else if (c == C_STICK) {
            int i = (int)(v >> 8);
            p.x += _stickTouchOffset[i].x; p.y += _stickTouchOffset[i].y;
            _stickNow[i] = p;
            if (i || _tabletPad) {
                CGPoint centre = _floatingCentre[i];
                CGFloat d = dist(p, centre), r = [self stickR:i];
                if (d > r) {
                    centre = CGPointMake(p.x - (p.x - centre.x) * r / d, p.y - (p.y - centre.y) * r / d);
                    if (_tabletPad && self.u > 0) centre = [self clampTabletStick:centre right:i != 0];
                    _floatingCentre[i] = centre;
                }
            }
        }
        else if (c == C_GAME) game = YES;
    }
    if (game) [self pushGame];
    [self recompute];
}
- (void)endTouches:(NSSet<UITouch *> *)ts tapped:(BOOL)ended {
    BOOL swap = NO, game = NO;
    for (UITouch *t in ts) {
        uint64_t v = [_owner objectForKey:t].unsignedLongLongValue;
        if (ended && (v & 0xff) == C_SWAP && [self inSwap:[t locationInView:self]]) swap = YES;   // layout button: counts only when released on the button
        if (ended && (v & 0xff) == C_ACTION) {
            int i = (int)(v >> 8);
            if (i <= DM_ACTION_RUNE_MENU || i == DM_ACTION_LOCK) {
                BOOL right = dm_action_buttons[i].right;
                CGPoint local = [self actionLocal:[t locationInView:self] right:right];
                if (dm_action_hit(right, local.x, local.y) == i) dm_action_toggle(&_actionInput, i);
            }
        }
        if ((v & 0xff) == C_GAME && (v >> 8) < 16) { _game[v >> 8] = nil; game = YES; }
        [_owner removeObjectForKey:t]; [_faceOf removeObjectForKey:t]; for (int i = 0; i < 2; i++) if (t == _stick[i]) _stick[i] = nil;
    }
    if (game) [self pushGame];
    [self recompute];
    if (swap) [self nextLayout];
}
- (void)touchesEnded:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e { [self endTouches:ts tapped:YES]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e { [self endTouches:ts tapped:NO]; }
- (void)reset { dm_action_clear(&_actionInput); [_owner removeAllObjects]; [_faceOf removeAllObjects]; _stick[0] = _stick[1] = nil; for (int i = 0; i < 16; i++) _game[i] = nil; [self pushGame]; [self recompute]; }

// ---- Shapes ----
static CGPathRef circlePath(CGPoint c, CGFloat r) { return CGPathCreateWithEllipseInRect(CGRectMake(c.x - r, c.y - r, 2 * r, 2 * r), NULL); }
static CGPathRef dropPath(CGPoint c, CGFloat r, CGFloat tipAngle, CGFloat round) {   // teardrop: circle + two tangents meeting at the tip, tip slightly rounded
    CGFloat d = r * K_DROP_TIP, th = acos(r / d);
    CGPoint tip = CGPointMake(c.x + d * cos(tipAngle), c.y + d * sin(tipAngle));
    CGPoint p1 = CGPointMake(c.x + r * cos(tipAngle + th), c.y + r * sin(tipAngle + th)), p2 = CGPointMake(c.x + r * cos(tipAngle - th), c.y + r * sin(tipAngle - th));
    CGMutablePathRef p = CGPathCreateMutable();
    CGPathMoveToPoint(p, NULL, p2.x, p2.y);
    CGPathAddArcToPoint(p, NULL, tip.x, tip.y, p1.x, p1.y, round);
    CGPathAddArc(p, NULL, c.x, c.y, r, tipAngle + th, tipAngle - th + 2 * M_PI, false);
    CGPathCloseSubpath(p); return p;
}
static CGPathRef armPath(CGPoint c, CGFloat R, CGFloat w, CGFloat in, CGFloat angle, CGFloat round) {   // one D-pad arm: an upward pentagon (tip toward the centre) rotated by angle around the centre
    CGPoint v[5] = {{-w, -R}, {w, -R}, {w, -(in + w)}, {0, -in}, {-w, -(in + w)}};
    CGFloat cs = cos(angle), sn = sin(angle);
    for (int i = 0; i < 5; i++) v[i] = CGPointMake(c.x + v[i].x * cs - v[i].y * sn, c.y + v[i].x * sn + v[i].y * cs);
    CGMutablePathRef p = CGPathCreateMutable();
    CGPathMoveToPoint(p, NULL, (v[4].x + v[0].x) / 2, (v[4].y + v[0].y) / 2);
    for (int i = 0; i < 5; i++) CGPathAddArcToPoint(p, NULL, v[i].x, v[i].y, v[(i + 1) % 5].x, v[(i + 1) % 5].y, round);
    CGPathCloseSubpath(p); return p;
}
static void setPath(CAShapeLayer *l, CGPathRef p) { l.path = p; l.shadowPath = p; CGPathRelease(p); }
static void placeLabel(CATextLayer *t, CGPoint c, CGFloat fs) {
    CTFontRef f = CTFontCreateUIFontForLanguage(kCTFontUIFontEmphasizedSystem, fs, NULL);
    t.font = f; t.fontSize = fs;
    CGFloat h = CTFontGetAscent(f) + CTFontGetDescent(f) + CTFontGetLeading(f), w = fs * 3;
    t.frame = CGRectMake(c.x - w / 2, c.y - h / 2, w, h);
    CFRelease(f);
}

- (void)layoutSubviews {
    [super layoutSubviews];
    UIWindowScene *ws = self.window.windowScene; if (!_preview && ws) atomic_store(&g_iface_orient, (int)ws.effectiveGeometry.interfaceOrientation);
    CGFloat u = self.u;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    _controls.frame = self.layer.bounds;
    for (int b = B_A; b <= B_Y; b++) { CGPoint c = [self facePos:b]; setPath(_key[b], circlePath(c, self.faceR)); placeLabel(_label[b], c, 20 * u); }
    for (int i = 0; i < (int)(sizeof k_btns / sizeof *k_btns); i++) { int b = k_btns[i];
        if (isDrop(b)) {
            BOOL right = b == B_ZR || b == B_R; CGPoint c = [self dropCenter:b];
            setPath(_key[b], _tabletPad ? circlePath(c, [self dropR:b]) : dropPath(c, [self dropR:b], right ? -M_PI_4 : -3 * M_PI_4, 4 * u));
            placeLabel(_label[b], c, 16 * u);
        } else if (isClick(b)) {
            CGPoint c = [self clickCenter:b]; setPath(_key[b], circlePath(c, self.clickR)); placeLabel(_label[b], c, 13 * u);
        } else {
            CGRect rc = [self pillRect:b];
            setPath(_key[b], CGPathCreateWithRoundedRect(rc, rc.size.height / 2, rc.size.height / 2, NULL)); placeLabel(_label[b], CGPointMake(CGRectGetMidX(rc), CGRectGetMidY(rc)), 18 * u);
        }
    }
    for (int i = 0; i < DM_TABLET_DIRECTIONS; i++) {
        int b = k_tabletDirections[i];
        CGPoint c = self.dpadCenter;
        if (_tabletPad) {
            DmTabletPoint offset = dm_tablet_dpad_offset(i);
            c = CGPointMake(c.x + offset.x * u, c.y + offset.y * u);
            setPath(_key[b], circlePath(c, self.faceR));
            placeLabel(_label[b], c, 20 * u);
        } else {
            setPath(_key[b], armPath(c, self.dpadR, K_ARM_W * u, K_ARM_IN * u, i * M_PI_2, 6 * u));
        }
    }
    CGPoint sc = self.swapCenter;
    if (_hasActionPad) {
        CGRect pill = CGRectMake(sc.x - 26, sc.y - 16, 52, 32);
        setPath(_swap, CGPathCreateWithRoundedRect(pill, 16, 16, NULL)); placeLabel(_swapLabel, sc, 13);
        _swapLabel.frame = CGRectInset(_swapLabel.frame, -7, 0);
    } else {
        setPath(_swap, circlePath(sc, K_SWAP_R * u)); placeLabel(_swapLabel, sc, 12 * u);
    }
    if (_actionPad) {
        CGFloat scale = self.actionScale, r = DM_ACTION_RADIUS * scale;
        for (int i = 0; i < DM_ACTION_COUNT; i++) {
            DmActionButton b = dm_action_buttons[i];
            CGPoint c = [self actionPoint:b.right x:b.x y:b.y];
            setPath(_actionKey[i], circlePath(c, r));
            if ([_actionIcon[i] isKindOfClass:CATextLayer.class]) placeLabel((CATextLayer *)_actionIcon[i], c, 18 * scale);
            else _actionIcon[i].frame = CGRectMake(c.x - r * 0.84, c.y - r * 0.84, r * 1.68, r * 1.68);
            if (i < 3) placeLabel(_actionCycle[i], CGPointMake(c.x - r * 0.57, c.y - r * 0.51), 12 * scale);
            CGPoint tag = CGPointMake(c.x + r * 0.68, c.y - r * 0.72);
            CGRect pill = CGRectMake(tag.x - 10 * scale, tag.y - 5.5 * scale, 20 * scale, 11 * scale);
            setPath(_actionBadge[i], CGPathCreateWithRoundedRect(pill, 5.5 * scale, 5.5 * scale, NULL));
            placeLabel(_actionLabel[i], tag, 9 * scale);
        }
    }
    if (!_tabletPad) setPath(_ring, circlePath([self stickCentre:0], [self stickR:0]));
    CGFloat k = _actionPad ? DM_ACTION_KNOB_R * self.actionScale : (_tabletPad ? DM_TABLET_KNOB_R : K_KNOB_R) * u;
    _knob.bounds = CGRectMake(0, 0, 2 * k, 2 * k);
    setPath(_knob, circlePath(CGPointMake(k, k), k));
    if (_tabletPad) {
        CGFloat r = [self stickR:0];
        _ring.bounds = _rightRing.bounds = CGRectMake(0, 0, 2 * r, 2 * r);
        setPath(_ring, circlePath(CGPointMake(r, r), r));
        setPath(_rightRing, circlePath(CGPointMake(r, r), r));
        _rightKnob.bounds = _knob.bounds;
        setPath(_rightKnob, circlePath(CGPointMake(k, k), k));
    }
    CAShapeLayer *in = (CAShapeLayer *)_knob.sublayers.firstObject; CGPathRef ip = circlePath(CGPointMake(k, k), k * 0.62);
    in.frame = _knob.bounds; in.path = ip; CGPathRelease(ip);
    [CATransaction commit];
    [self refresh];
}
- (void)safeAreaInsetsDidChange { [super safeAreaInsetsDidChange]; [self setNeedsLayout]; }
- (void)refresh {   // pressed state → fill, sticks → knob position
    uint64_t all = _faceBits | _dpadBits | _btnBits;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    for (int b = 0; b < B_N; b++) { BOOL on = (all >> b) & 1;
        _key[b].fillColor = (on ? k_on : k_idle).CGColor; _label[b].foregroundColor = (on ? k_textOn : k_text).CGColor; }
    if (_actionPad) for (int i = 0; i < DM_ACTION_COUNT; i++) {
        BOOL on = (_actionHeld >> i) & 1;
        if (i <= DM_ACTION_RUNE_MENU) on = (_actionInput.menu >> dm_action_buttons[i].button) & 1;
        else if (i == DM_ACTION_LOCK) on = _actionInput.lock;
        UIColor *tint = i == DM_ACTION_LOCK ? UIColor.systemOrangeColor : UIColor.systemTealColor;
        _actionKey[i].strokeColor = [tint colorWithAlphaComponent:on ? 1 : 0.75].CGColor;
        _actionKey[i].fillColor = on ? [tint colorWithAlphaComponent:0.50].CGColor : k_idle.CGColor;
    }
    _swap.fillColor = (_swapHeld ? k_on : k_idle).CGColor; _swapLabel.foregroundColor = (_swapHeld ? k_textOn : k_text).CGColor;
    CGPoint h = [self stickCentre:0], o = [self knobOffset:0];
    _knob.position = CGPointMake(h.x + o.x, h.y + o.y); _knob.fillColor = (_stick[0] ? k_on : k_idle).CGColor;
    if (_tabletPad) {
        CGPoint home = [self stickCentre:1], offset = [self knobOffset:1];
        _ring.position = h; _rightRing.position = home;
        _rightKnob.position = CGPointMake(home.x + offset.x, home.y + offset.y);
        _rightKnob.fillColor = (_stick[1] ? k_on : k_idle).CGColor;
    }
    [CATransaction commit];
}

// ---- Physical controllers ----
// Each controller with an extended gamepad profile is a player of its own, as on the Mac (front_mac.m): it holds a slot (pad_slots.h: player 1 first, a reconnected controller
// gets its player back) and goes to dm_pad_set_player, and hle_hid.c reports player n on its own npad while the slot is held (dm_pad_players). Player 1's controller is ORed
// with the touch gamepad; a one-player game that supports only No1 / Handheld still sees every controller as player 1 (hle_hid.c). Each player has its controller's rumble and
// gyro; the phone's gyro is player 1's. With DM_PAD_MERGE=1 every controller is player 1, as before (the last one moved wins)
static pad_slots g_slots;
static GCController *g_held[DM_PLAYERS];   // the controller of each slot, kept alive while it holds it (the slot table keys on its pointer)
static int g_merge;
static int32_t axis(float v) { return (int32_t)(fmaxf(-1.f, fminf(1.f, v)) * 32767); }
static void read_pad(GCExtendedGamepad *g) {
    int p = g_merge ? 0 : pad_slot_of(&g_slots, (__bridge const void *)g.controller); if (p < 0) return;
    dm_haptics_apple_controller(p, g.controller);
    _Static_assert(DM_BTN_A == 1u << B_A && DM_BTN_B == 1u << B_B && DM_BTN_X == 1u << B_X && DM_BTN_Y == 1u << B_Y, "face button bits");
    uint64_t m = dm_pad_face(g);   // by position, a Nintendo pad by its labels
    #define K(btn, bit) if (btn.isPressed) m |= 1ull << bit
    K(g.leftShoulder, B_L); K(g.rightShoulder, B_R); K(g.leftTrigger, B_ZL); K(g.rightTrigger, B_ZR);
    K(g.buttonMenu, B_PLUS); if (g.buttonOptions) K(g.buttonOptions, B_MINUS);
    if (g.leftThumbstickButton) K(g.leftThumbstickButton, B_LS); if (g.rightThumbstickButton) K(g.rightThumbstickButton, B_RS);
    K(g.dpad.left, B_LEFT); K(g.dpad.up, B_UP); K(g.dpad.right, B_RIGHT); K(g.dpad.down, B_DOWN);
    #undef K
    dm_pad_set_player(p, m, axis(g.leftThumbstick.xAxis.value), axis(g.leftThumbstick.yAxis.value), axis(g.rightThumbstick.xAxis.value), axis(g.rightThumbstick.yAxis.value));
}
// Home and Capture: without this iOS takes them as system gestures (Home opens the Games overlay, Capture a screenshot); the app gives them no function
static void pad_keep_system_buttons(GCController *c) { for (NSString *b in @[GCInputButtonHome, GCInputButtonShare]) c.physicalInputProfile.buttons[b].preferredSystemGestureState = GCSystemGestureStateDisabled; }
static const char *pad_name(GCController *c) { return c.vendorName.UTF8String ?: "?"; }
static void npad_name(int p, char *out, size_t cap) { uint32_t id = dm_player_npad(p); if (id == 0x20) snprintf(out, cap, "handheld"); else snprintf(out, cap, "%u", id); }
static void pads_start(void) {
    const char *e = getenv("DM_PAD_MERGE"); g_merge = e && atoi(e);
    LOG("front end: %s", g_merge ? "every controller is player 1 (DM_PAD_MERGE)" : "each controller is a player of its own, the touch gamepad plays with player 1");
}
// Called at start and on every connect / disconnect (gone: the controller that was just removed, nil otherwise); returns whether a controller is in use
static BOOL pads_merged(GCController *gone) {
    if (gone) { gone.extendedGamepad.valueChangedHandler = nil; dm_motion_detach(gone, 0); }
    BOOL any = NO; int motion = 0;
    for (GCController *c in GCController.controllers) if (c != gone && c.extendedGamepad) {
        if (c.motion.hasRotationRate) motion = 1;
        any = YES; pad_keep_system_buttons(c); c.extendedGamepad.valueChangedHandler = ^(GCExtendedGamepad *g, GCControllerElement *el) { (void)el; read_pad(g); };
        dm_motion_attach(c, 0);   // every controller is player 1: the last one moved drives its six-axis sensor
        read_pad(c.extendedGamepad);
    }
    if (!any || !motion) dm_motion_clear(0);   // the phone's gyro (if on) takes over from its next sample
    if (!any) { dm_haptics_apple_controller(0, nil); dm_pad_set(0, 0, 0, 0, 0); }
    return any;
}
static BOOL pads_slotted(GCController *gone) {
    NSArray<GCController *> *now = GCController.controllers; char nb[16];
    for (int p = 0; p < DM_PLAYERS; p++) if (g_held[p] && (g_held[p] == gone || ![now containsObject:g_held[p]])) {
        npad_name(p, nb, sizeof nb); LOG("controller '%s' disconnected: player %d (npad %s) is free", pad_name(g_held[p]), p + 1, nb);
        g_held[p].extendedGamepad.valueChangedHandler = nil;
        dm_motion_detach(g_held[p], p);   // player 1's: the phone's gyro (if on) takes over from its next sample
        dm_haptics_apple_controller(p, nil);
        pad_slot_free(&g_slots, (__bridge const void *)g_held[p]); g_held[p] = nil;
        dm_pad_set_player(p, 0, 0, 0, 0, 0);   // nothing stays pressed
    }
    for (GCController *c in now) if (c.extendedGamepad && c != gone && pad_slot_of(&g_slots, (__bridge const void *)c) < 0) {
        int p = pad_slot_take(&g_slots, (__bridge const void *)c, pad_name(c));
        if (p < 0) { LOG("controller '%s' connected: all %d players are taken, not used", pad_name(c), DM_PLAYERS); continue; }
        g_held[p] = c; pad_keep_system_buttons(c);
        c.extendedGamepad.valueChangedHandler = ^(GCExtendedGamepad *g, GCControllerElement *el) { (void)el; read_pad(g); };
        dm_motion_attach(c, p);
        npad_name(p, nb, sizeof nb); LOG("controller '%s' connected: player %d (npad %s)%s", pad_name(c), p + 1, nb, c.motion.hasRotationRate ? ", with motion (gyro)" : "");
        read_pad(c.extendedGamepad);
    }
    dm_pad_players(pad_slot_mask(&g_slots));
    return pad_slot_mask(&g_slots) != 0;
}
- (void)padsChanged:(NSNotification *)note {
    GCController *c = note.object, *gone = [note.name isEqual:GCControllerDidDisconnectNotification] ? c : nil;
    if (c && (!c.extendedGamepad || g_merge)) LOG("controller %s: %s%s", gone ? "disconnected" : "connected", pad_name(c), c.extendedGamepad ? "" : " (no extended gamepad profile: not used)");
    BOOL any = g_merge ? pads_merged(gone) : pads_slotted(gone);
    dispatch_async(dispatch_get_main_queue(), ^{
        self->_padOff = any;
        self->_controls.hidden = self->_padOff;
        [self reset];
    });
}
@end

UIView *dm_gamepad_view(CGRect frame) { DmGamepad *v = [[DmGamepad alloc] initWithFrame:frame preview:NO]; g_view = v; return v; }
UIView *dm_tablet_pad_preview(void) { return [[DmGamepad alloc] initWithFrame:CGRectZero preview:YES]; }
void dm_tablet_pad_preview_update(UIView *view, double size, double lift) {
    [(DmGamepad *)view setTabletSize:size lift:lift];
}
void dm_gamepad_active(void) { dispatch_async(dispatch_get_main_queue(), ^{ for (GCController *c in GCController.controllers) dm_motion_rearm(c); }); }   // On become active: motion_apple.h
void dm_gamepad_reset(void) {   // On resign active: release everything (a key held while switching away and released in background gets no "release")
    dispatch_async(dispatch_get_main_queue(), ^{ [g_view reset]; });
    pthread_mutex_lock(&g_mu); g_shake_btn = 0; pthread_mutex_unlock(&g_mu); publish();
    if (g_merge) dm_pad_set(0, 0, 0, 0, 0);
    else for (int p = 0; p < DM_PLAYERS; p++) if (g_held[p]) dm_pad_set_player(p, 0, 0, 0, 0, 0);
}
