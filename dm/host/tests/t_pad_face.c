// The iOS face-button option is applied after the controller's normal mapping.
#include "../pad_apple.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    const uint64_t face[] = {DM_BTN_A, DM_BTN_B, DM_BTN_X, DM_BTN_Y};
    const uint64_t flipped[] = {DM_BTN_B, DM_BTN_A, DM_BTN_Y, DM_BTN_X};
    for (int labelled = 0; labelled <= 1; labelled++) {
        const uint64_t *normal = labelled ? face : flipped;
        const uint64_t *swapped = labelled ? flipped : face;
        for (unsigned mask = 0; mask < 16; mask++) {
            uint64_t named = 0, off = 0, on = 0;
            for (unsigned i = 0; i < 4; i++) if (mask & (1u << i)) {
                named |= face[i]; off |= normal[i]; on |= swapped[i];
            }
            assert(dm_pad_map_face(named, labelled, 0) == off);
            assert(dm_pad_map_face(named, labelled, 1) == on);
        }
    }
    puts("t_pad_face OK");
    return 0;
}
