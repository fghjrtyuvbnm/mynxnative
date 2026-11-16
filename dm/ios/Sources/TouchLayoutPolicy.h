#ifndef DM_TOUCH_LAYOUT_POLICY_H
#define DM_TOUCH_LAYOUT_POLICY_H
typedef enum { DM_BOTW_IPAD_3D, DM_BOTW_ACTION, DM_BOTW_CLASSIC_3D, DM_BOTW_LAYOUT_COUNT } DmBotwLayout;
static inline DmBotwLayout dm_botw_saved_layout(long saved) {
    // The original preference was a boolean: false for iPad 3D, true for Action.
    return saved >= 0 && saved < DM_BOTW_LAYOUT_COUNT ? (DmBotwLayout)saved : DM_BOTW_IPAD_3D;
}
static inline DmBotwLayout dm_botw_next_layout(DmBotwLayout layout) {
    return (DmBotwLayout)((layout + 1) % DM_BOTW_LAYOUT_COUNT);
}
static inline int dm_initial_pad_layout(int profile, int saved, int has_saved, int handheld, int touch_only) {
    if (touch_only && handheld) return 2;
    int layout = has_saved ? saved : profile;
    return layout == 2 && !handheld ? 0 : layout;
}
static inline int dm_layout_switch_visible(int tap, int touch_only) {
    return !(tap && touch_only);
}
#endif
