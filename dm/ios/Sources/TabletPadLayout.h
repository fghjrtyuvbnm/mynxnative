#ifndef DM_TABLET_PAD_LAYOUT_H
#define DM_TABLET_PAD_LAYOUT_H

// X starts at the near safe-area edge. Y is measured upward from its vertical midpoint.
enum {
    DM_TABLET_STICK_X = 86, DM_TABLET_STICK_Y = 0, DM_TABLET_STICK_R = 56,
    DM_TABLET_STICK_MIN_X = 56, DM_TABLET_STICK_MAX_X = 146,
    DM_TABLET_STICK_MIN_Y = -24, DM_TABLET_STICK_MAX_Y = 24,
    DM_TABLET_FACE_X = 93, DM_TABLET_FACE_Y = -166, DM_TABLET_FACE_GAP = 44, DM_TABLET_FACE_R = 24,
    DM_TABLET_SHOULDER_OUT_X = 50, DM_TABLET_SHOULDER_IN_X = 128,
    DM_TABLET_SHOULDER_Y = 116, DM_TABLET_SHOULDER_R = 24,
    DM_TABLET_CLICK_X = 230, DM_TABLET_CLICK_R = 18,
    DM_TABLET_MENU_X = 205, DM_TABLET_MENU_Y = -110, DM_TABLET_MENU_W = 48, DM_TABLET_MENU_H = 36,
    DM_TABLET_KNOB_R = 24
};

enum { DM_TABLET_UP, DM_TABLET_RIGHT, DM_TABLET_DOWN, DM_TABLET_LEFT, DM_TABLET_DIRECTIONS };
typedef struct { double x, y; } DmTabletPoint;

static inline DmTabletPoint dm_tablet_dpad_offset(int direction) {
    static const DmTabletPoint offsets[DM_TABLET_DIRECTIONS] = {
        {0, -DM_TABLET_FACE_GAP}, {DM_TABLET_FACE_GAP, 0},
        {0, DM_TABLET_FACE_GAP}, {-DM_TABLET_FACE_GAP, 0}
    };
    return offsets[direction];
}

static inline unsigned dm_tablet_dpad_at(double x, double y) {
    // A small overlap between adjacent hit circles accepts a one-thumb diagonal.
    const double radius = DM_TABLET_FACE_R * 1.35;
    unsigned mask = 0;
    for (int i = 0; i < DM_TABLET_DIRECTIONS; i++) {
        DmTabletPoint p = dm_tablet_dpad_offset(i);
        double dx = x - p.x, dy = y - p.y;
        if (dx * dx + dy * dy <= radius * radius) mask |= 1u << i;
    }
    return mask;
}
static inline int dm_tablet_stick_contains(double x, double y) {
    double dx = x - DM_TABLET_STICK_X, dy = y - DM_TABLET_STICK_Y;
    return dx * dx + dy * dy <= DM_TABLET_STICK_R * DM_TABLET_STICK_R ||
           (x >= DM_TABLET_STICK_MIN_X && x <= DM_TABLET_STICK_MAX_X &&
            y >= DM_TABLET_STICK_MIN_Y && y <= DM_TABLET_STICK_MAX_Y);
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

typedef struct { double scale, centre; } DmTabletMetrics;

static inline DmTabletMetrics dm_tablet_pad_metrics(double width, double height, double size, double lift) {
    if (width <= 0 || height <= 0) return (DmTabletMetrics){0, 0};
    if (size != 90 && size != 110) size = 100;
    if (lift != -24 && lift != 24) lift = 0;
    double scale = dm_tablet_pad_scale(width, height) * (size / 100);
    // Leave room for both control groups and all three height choices.
    if (scale > width / 540) scale = width / 540;
    if (scale > height / 630) scale = height / 630;
    return (DmTabletMetrics){scale, height / 2 + lift * scale};
}

static inline double dm_tablet_pad_y(DmTabletMetrics metrics, double y) {
    return metrics.centre + y * metrics.scale;
}

#endif
