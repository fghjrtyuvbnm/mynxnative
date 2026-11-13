#ifndef DM_BOTW_ACTION_PAD_H
#define DM_BOTW_ACTION_PAD_H

#include <math.h>
#include <stdint.h>

enum { B_A = 0, B_B, B_X, B_Y, B_LS, B_RS, B_L, B_R, B_ZL, B_ZR, B_PLUS, B_MINUS, B_LEFT, B_UP, B_RIGHT, B_DOWN, B_N };
enum { DM_ACTION_WEAPON, DM_ACTION_SHIELD, DM_ACTION_RUNE_MENU, DM_ACTION_ZL,
       DM_ACTION_RUNE, DM_ACTION_LOCK, DM_ACTION_CANCEL, DM_ACTION_MAP, DM_ACTION_CROUCH,
       DM_ACTION_BOW, DM_ACTION_ATTACK, DM_ACTION_JUMP, DM_ACTION_INTERACT, DM_ACTION_RUN,
       DM_ACTION_BAG, DM_ACTION_SCOPE, DM_ACTION_THROW, DM_ACTION_WHISTLE, DM_ACTION_COUNT };
enum { DM_ACTION_RADIUS = 21, DM_ACTION_STICK_R = 2 * DM_ACTION_RADIUS, DM_ACTION_KNOB_R = 20 };
enum { DM_ACTION_STICK_TRAVEL = 7 };

typedef struct { int x, y, right, button; } DmActionButton;
static const DmActionButton dm_action_buttons[DM_ACTION_COUNT] = {
    {46,-99,0,B_RIGHT}, {95,-99,0,B_LEFT}, {144,-99,0,B_UP},
    {29,-42,0,B_ZL}, {166,-42,0,B_L}, {215,-42,0,B_ZL},
    {25,42,0,B_B}, {47,101,0,B_MINUS}, {96,101,0,B_LS},
    {100,-99,1,B_ZR}, {33,-41,1,B_Y}, {48,-99,1,B_X}, {28,27,1,B_A},
    {45,101,1,B_B}, {94,101,1,B_PLUS}, {143,101,1,B_RS},
    {177,-41,1,B_R}, {145,101,0,B_DOWN},
};

static inline double dm_action_scale(double w, double h) { return fmax(0, fmin(h / 550, w / 500)); }
static inline double dm_action_stick_x(int right) { return right ? 102 : 95; }
static inline int dm_action_hit(int right, double x, double y) {
    int best = -1;
    double limit = DM_ACTION_RADIUS + 3;
    for (int i = 0; i < DM_ACTION_COUNT; ++i) {
        DmActionButton a = dm_action_buttons[i];
        if (a.right != right) continue;
        double distance = hypot(x - a.x, y - a.y);
        if (distance <= limit) { limit = distance; best = i; }
    }
    return best;
}
static inline int dm_action_stick_contains(int right, double x, double y) {
    return hypot(x - dm_action_stick_x(right), y) <= DM_ACTION_STICK_R + 4;
}
static inline void dm_action_stick_clamp(int right, double *x, double *y) {
    double home = dm_action_stick_x(right);
    double dx = *x - home;
    double distance = hypot(dx, *y);
    if (distance > DM_ACTION_STICK_TRAVEL) {
        double scale = DM_ACTION_STICK_TRAVEL / distance;
        *x = home + dx * scale;
        *y *= scale;
    }
}

typedef struct { int lock; uint64_t menu; } DmActionInput;
static inline void dm_action_toggle(DmActionInput *input, int action) {
    if (action == DM_ACTION_LOCK) input->lock = !input->lock;
    else if (action >= DM_ACTION_WEAPON && action <= DM_ACTION_RUNE_MENU) {
        uint64_t bit = UINT64_C(1) << dm_action_buttons[action].button;
        input->menu = input->menu == bit ? 0 : bit;
    }
}
static inline uint64_t dm_action_bits(DmActionInput input) {
    return input.menu | ((uint64_t)input.lock << B_ZL);
}
/* Breath of the Wild reads the guest's right stick for quick selection. */
static inline void dm_action_route_sticks(DmActionInput input, int32_t axes[4]) {
    if (!input.menu) return;
    axes[2] = axes[0];
    axes[3] = axes[1];
    axes[0] = 0;
    axes[1] = 0;
}
static inline void dm_action_clear(DmActionInput *input) { *input = (DmActionInput){0}; }
#endif
