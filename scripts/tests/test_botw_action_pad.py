"""Check the action layout geometry and input policy used by the iOS overlay."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "dm/ios/Sources"


class BotwActionPad(unittest.TestCase):
    def test_overlay_uses_action_policy_and_clears_held_input(self):
        text = (SOURCE / "DmGamepad.m").read_text(encoding="utf-8")
        self.assertIn('#include "BotwActionPad.h"', text)
        self.assertIn('@"org.nxnative.01007ef00011e000.v190"', text)
        self.assertIn('setBool:_actionPad forKey:k_botw_layout_key', text)
        self.assertIn('dm_action_clear(&_actionInput)', text.split('- (void)reset {')[1])
        self.assertIn('dm_action_bits(_actionInput)', text)
        self.assertTrue('dm_action_route_sticks(_actionInput, ax)' in text)

    def test_geometry_and_independent_latches(self):
        source = r"""
#if __has_include("BotwActionPad.h")
#include "BotwActionPad.h"
#include <assert.h>
int main(void) {
    const double windows[][2] = {{1133, 720}, {600, 420}, {480, 320}};
    for (unsigned w = 0; w < 3; ++w) {
        double width = windows[w][0], height = windows[w][1];
        double scale = dm_action_scale(width, height);
        for (int i = 0; i < DM_ACTION_COUNT; ++i) {
            DmActionButton a = dm_action_buttons[i];
            assert((fabs((double)a.y) + DM_ACTION_RADIUS + 6) * scale <= height / 5);
            assert((a.x + DM_ACTION_RADIUS) * scale < width / 2);
            assert(a.x > DM_ACTION_RADIUS);
            assert(hypot(a.x - dm_action_stick_x(a.right), a.y)
                   >= DM_ACTION_RADIUS + DM_ACTION_STICK_R);
            assert(dm_action_hit(a.right, a.x, a.y) == i);
            for (int j = 0; j < i; ++j) {
                DmActionButton b = dm_action_buttons[j];
                if (a.right == b.right)
                    assert(hypot(a.x - b.x, a.y - b.y) >= 2 * DM_ACTION_RADIUS);
            }
        }
    }
    assert(dm_action_scale(1133, 720) * 2 * DM_ACTION_RADIUS >= 54);
    assert(dm_action_stick_contains(0, dm_action_stick_x(0), 0));
    assert(dm_action_stick_contains(1, dm_action_stick_x(1), 0));
    assert(!dm_action_stick_contains(1, 200, 0));
    DmActionInput input = {0};
    dm_action_toggle(&input, DM_ACTION_LOCK);
    dm_action_toggle(&input, DM_ACTION_WEAPON);
    assert(dm_action_bits(input) == ((1u << B_ZL) | (1u << B_RIGHT)));
    dm_action_toggle(&input, DM_ACTION_SHIELD);
    assert(dm_action_bits(input) == ((1u << B_ZL) | (1u << B_LEFT)));
    dm_action_toggle(&input, DM_ACTION_SHIELD);
    assert(dm_action_bits(input) == (1u << B_ZL));
    for (int menu = DM_ACTION_WEAPON; menu <= DM_ACTION_RUNE_MENU; ++menu) {
        dm_action_toggle(&input, menu);
        /* A held bow trigger combines with the quick menu and lock bits. */
        uint64_t buttons = (1u << B_ZR) | dm_action_bits(input);
        assert(buttons == ((1u << B_ZR) | (1u << B_ZL) | (1u << dm_action_buttons[menu].button)));
        int32_t sticks[] = {-12345, 23456, 300, -900};
        dm_action_route_sticks(input, sticks);
        assert(sticks[0] == 0 && sticks[1] == 0 && sticks[2] == -12345 && sticks[3] == 23456);
        dm_action_toggle(&input, menu);
        int32_t movement[] = {100, -200, -300, 400};
        dm_action_route_sticks(input, movement);
        assert(movement[0] == 100 && movement[1] == -200 && movement[2] == -300 && movement[3] == 400);
    }
    dm_action_toggle(&input, DM_ACTION_RUNE_MENU);
    dm_action_clear(&input);
    assert(dm_action_bits(input) == 0);
    int32_t sticks[] = {100, -200, -300, 400};
    dm_action_route_sticks(input, sticks);
    assert(sticks[0] == 100 && sticks[1] == -200 && sticks[2] == -300 && sticks[3] == 400);
    return 0;
}
#else
int main(void) { return 42; }
#endif
"""
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp) / "pad.c"
            exe = c.with_suffix(".exe")
            c.write_text(source)
            build = subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                                    "-I", str(SOURCE), str(c), "-o", str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, "42: action layout absent; " + run.stderr)


if __name__ == "__main__":
    unittest.main()
