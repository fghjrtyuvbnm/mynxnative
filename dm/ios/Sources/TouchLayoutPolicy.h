#ifndef DM_TOUCH_LAYOUT_POLICY_H
#define DM_TOUCH_LAYOUT_POLICY_H
static inline int dm_initial_pad_layout(int profile, int saved, int has_saved, int handheld, int touch_only) {
    if (touch_only && handheld) return 2;
    int layout = has_saved ? saved : profile;
    return layout == 2 && !handheld ? 0 : layout;
}
static inline int dm_layout_switch_visible(int tap, int touch_only) {
    return !(tap && touch_only);
}
#endif
