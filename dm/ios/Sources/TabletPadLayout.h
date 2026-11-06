#ifndef DM_TABLET_PAD_LAYOUT_H
#define DM_TABLET_PAD_LAYOUT_H

// Distance from the near side and the bottom of the safe area, in layout points.
enum {
    DM_TABLET_STICK_X = 86, DM_TABLET_STICK_Y = 86, DM_TABLET_STICK_R = 56,
    DM_TABLET_FACE_X = 93, DM_TABLET_FACE_Y = 235, DM_TABLET_FACE_GAP = 44, DM_TABLET_FACE_R = 24,
    DM_TABLET_DPAD_R = 41,
    DM_TABLET_SHOULDER_OUT_X = 50, DM_TABLET_SHOULDER_IN_X = 128,
    DM_TABLET_SHOULDER_Y = 352, DM_TABLET_SHOULDER_R = 24,
    DM_TABLET_CLICK_X = 178, DM_TABLET_CLICK_R = 18,
    DM_TABLET_MENU_X = 199, DM_TABLET_MENU_Y = 182, DM_TABLET_MENU_W = 48, DM_TABLET_MENU_H = 36,
    DM_TABLET_KNOB_R = 24
};
static const double DM_TABLET_STICK_GRAB = 1.14;

static inline double dm_tablet_pad_scale(double width, double height) {
    double scale = width / 640.0;
    if (height / 650.0 < scale) scale = height / 650.0;
    return scale < 1.05 ? scale : 1.05;
}

#endif
