// A physical controller's face buttons as Switch buttons, shared by the Mac front end (front_mac.m) and the iOS gamepad (DmGamepad.m). GameController names most pads' face
// buttons by position, as on an Xbox pad (buttonA bottom, buttonB right, buttonX left, buttonY top), but a Nintendo pad's by their printed labels (buttonA is the right
// button, marked A): a Switch Pro Controller (or a pad that presents itself as one) and Joy-Con (productCategory "Nintendo Switch Joy-Con (L)", "(R)", "(L/R)").
// The Switch's layout is right A, bottom B, top X, left Y, so a Nintendo pad maps name for name and any other pad by position. Checked with a Pro Controller on the Mac
// and on iOS (PR #650). Open: a single Joy-Con held sideways is matched too and has not been tried; if GameController keeps its labels there instead of turning them
// with the controller, its face buttons come out a quarter turn off.
#pragma once
#include <stdint.h>
#include "dm_input.h"

// Input bits here describe GameController button names; output bits describe Switch actions.
static inline uint64_t dm_pad_map_face(uint64_t named, int labelled, int swap) {
    if (!!labelled != !!swap) return named;
    return ((named & (DM_BTN_A | DM_BTN_X)) << 1) | ((named & (DM_BTN_B | DM_BTN_Y)) >> 1);
}

#ifdef __OBJC__
#import <GameController/GameController.h>
#include <TargetConditionals.h>
#include <stdlib.h>

static inline int dm_pad_labelled(GCController *c) {
    NSString *k = c.productCategory;
    return [k isEqualToString:@"Switch Pro Controller"] || [k containsString:@"Joy-Con"];
}
// DM_BTN_A / B / X / Y of the pad's pressed face buttons
static inline uint64_t dm_pad_face(GCExtendedGamepad *g) {
    uint64_t named = (g.buttonA.isPressed ? DM_BTN_A : 0) | (g.buttonB.isPressed ? DM_BTN_B : 0)
                   | (g.buttonX.isPressed ? DM_BTN_X : 0) | (g.buttonY.isPressed ? DM_BTN_Y : 0);
    int swap = 0;
#if TARGET_OS_IOS
    const char *v = getenv("DM_PAD_SWAP_FACE");
    swap = v && v[0] == '1' && v[1] == '\0';
#endif
    return dm_pad_map_face(named, dm_pad_labelled(g.controller), swap);
}
#endif
