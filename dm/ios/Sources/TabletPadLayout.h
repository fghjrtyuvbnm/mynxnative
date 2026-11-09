#ifndef DM_TABLET_PAD_LAYOUT_H
#define DM_TABLET_PAD_LAYOUT_H

// Distance from the near side and the bottom of the safe area, in layout points.
enum {
    DM_TABLET_STICK_X = 86, DM_TABLET_STICK_Y = 146, DM_TABLET_STICK_R = 56,
    DM_TABLET_STICK_MIN_X = 56, DM_TABLET_STICK_MAX_X = 146,
    DM_TABLET_STICK_MIN_Y = 116, DM_TABLET_STICK_MAX_Y = 202,
    DM_TABLET_FACE_X = 93, DM_TABLET_FACE_Y = 295, DM_TABLET_FACE_GAP = 44, DM_TABLET_FACE_R = 24,
    DM_TABLET_DPAD_R = 41,
    DM_TABLET_SHOULDER_OUT_X = 50, DM_TABLET_SHOULDER_IN_X = 128,
    DM_TABLET_SHOULDER_Y = 406, DM_TABLET_SHOULDER_R = 24,  // Keep shoulder buttons within reach in shorter windows.
    DM_TABLET_CLICK_X = 178, DM_TABLET_CLICK_R = 18,
    DM_TABLET_MENU_X = 199, DM_TABLET_MENU_Y = 242, DM_TABLET_MENU_W = 48, DM_TABLET_MENU_H = 36,
    DM_TABLET_KNOB_R = 24
};
static inline int dm_tablet_stick_contains(double x, double y) {
    return x >= DM_TABLET_STICK_MIN_X && x <= DM_TABLET_STICK_MAX_X &&
           y >= DM_TABLET_STICK_MIN_Y && y <= DM_TABLET_STICK_MAX_Y;
}

static inline void dm_tablet_stick_clamp(double *x, double *y) {
    *x = *x < DM_TABLET_STICK_MIN_X ? DM_TABLET_STICK_MIN_X : *x > DM_TABLET_STICK_MAX_X ? DM_TABLET_STICK_MAX_X : *x;
    *y = *y < DM_TABLET_STICK_MIN_Y ? DM_TABLET_STICK_MIN_Y : *y > DM_TABLET_STICK_MAX_Y ? DM_TABLET_STICK_MAX_Y : *y;
}

static inline double dm_tablet_pad_scale(double width, double height) {
    double scale = width / 640.0;
    if (height / 650.0 < scale) scale = height / 650.0;
    return scale < 1.05 ? scale : 1.05;
}

#endif
