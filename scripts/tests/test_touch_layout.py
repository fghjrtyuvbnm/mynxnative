"""Exercise the same C layout policy called by the UIKit frontend."""
from pathlib import Path
import subprocess,tempfile,unittest
REPO=Path(__file__).resolve().parents[2]
class TouchLayout(unittest.TestCase):
    def test_physical_controller_hides_tablet_controls(self):
        source = (REPO / 'dm/ios/Sources/DmGamepad.m').read_text(encoding='utf-8')
        update = source.split('- (void)padsChanged:(NSNotification *)note {', 1)[1].split('@end', 1)[0]
        self.assertIn('self->_padOff = any;', update)
        self.assertIn('self->_controls.hidden = self->_padOff;', update)
        self.assertIn('[self reset];', update)

    def test_tablet_controls_fit_mini_and_smaller_windows(self):
        source = '''#if __has_include("TabletPadLayout.h")
#include "TabletPadLayout.h"
#include <math.h>

static int fits(double width, double height) {
    double scale = dm_tablet_pad_scale(width, height);
    double faceGrab = DM_TABLET_FACE_GAP + DM_TABLET_FACE_R * 1.6;
    if (DM_TABLET_STICK_MIN_X < DM_TABLET_STICK_R) return 1;
    if (DM_TABLET_STICK_MIN_Y - DM_TABLET_STICK_R <= DM_TABLET_FACE_Y + faceGrab) return 2;
    if (DM_TABLET_SHOULDER_Y - DM_TABLET_SHOULDER_R * 1.35 <= DM_TABLET_STICK_MAX_Y + DM_TABLET_STICK_R) return 3;
    if ((DM_TABLET_CLICK_X + DM_TABLET_CLICK_R * 1.35) * scale >= width / 2) return 4;
    if (DM_TABLET_CLICK_X - DM_TABLET_STICK_MAX_X <= DM_TABLET_CLICK_R * 1.35 + DM_TABLET_STICK_R) return 5;
    if (DM_TABLET_SHOULDER_IN_X-DM_TABLET_SHOULDER_OUT_X <= DM_TABLET_SHOULDER_R * 2.7) return 6;
    if (DM_TABLET_MENU_Y + DM_TABLET_MENU_H / 2 + 8 >= DM_TABLET_STICK_MIN_Y - DM_TABLET_STICK_R) return 7;
    return 0;
}

int main(void) {
    if (fits(1133, 720)) return fits(1133, 720);
    if (fits(600, 420)) return fits(600, 420) + 10;
    if (DM_TABLET_FACE_R * dm_tablet_pad_scale(1133, 720) * 2 < 44) return 20;
    for (int i = 0; i < DM_TABLET_DIRECTIONS; i++) {
        DmTabletPoint c = dm_tablet_dpad_offset(i);
        double edge = 1 + (double)DM_TABLET_FACE_R / DM_TABLET_FACE_GAP;
        if (dm_tablet_dpad_at(c.x, c.y) != (1u << i) ||
            dm_tablet_dpad_at(c.x * edge, c.y * edge) != (1u << i)) return 36;
        DmTabletPoint next = dm_tablet_dpad_offset((i + 1) % DM_TABLET_DIRECTIONS);
        if (dm_tablet_dpad_at((c.x + next.x) / 2, (c.y + next.y) / 2) !=
            ((1u << i) | (1u << ((i + 1) % DM_TABLET_DIRECTIONS)))) return 37;
    }
    if (dm_tablet_dpad_at(0, 0) || dm_tablet_dpad_at(0, -80)) return 38;
    if (!dm_tablet_stick_contains(DM_TABLET_STICK_X, DM_TABLET_STICK_Y)) return 22;
    if (!dm_tablet_stick_contains(40, 0) || !dm_tablet_stick_contains(86, -45)) return 28;
    if (dm_tablet_stick_contains(20, 0) || dm_tablet_stick_contains(86, -66)) return 29;
    double x = 130, y = 14;  /* a touch away from the idle centre */
    if (!dm_tablet_stick_contains(x, y)) return 23;
    dm_tablet_stick_clamp(&x, &y);
    if (x != 130 || y != 14) return 24;
    x = -100; y = 800;       /* the finger can drag past the region */
    if (dm_tablet_stick_contains(x, y)) return 25;
    dm_tablet_stick_clamp(&x, &y);
    if (x != DM_TABLET_STICK_MIN_X || y != DM_TABLET_STICK_MAX_Y) return 26;
    const double sizes[] = {90, 100, 110}, lifts[] = {-24, 0, 24};
    const double windows[][2] = {{1133, 720}, {600, 420}, {480, 320}};
    for (int w = 0; w < 3; w++) {
        double width = windows[w][0], height = windows[w][1];
        DmTabletMetrics normal = dm_tablet_pad_metrics(width, height, 100, 0);
        if (normal.scale != dm_tablet_pad_scale(width, height)) return 31;
        if (fabs(dm_tablet_pad_y(normal, DM_TABLET_STICK_Y) - height / 2) > 0.001) return 35;
        DmTabletMetrics invalid = dm_tablet_pad_metrics(width, height, -1, 999);
        if (invalid.scale != normal.scale || invalid.centre != normal.centre) return 32;
        for (int s = 0; s < 3; s++) for (int l = 0; l < 3; l++) {
            DmTabletMetrics m = dm_tablet_pad_metrics(width, height, sizes[s], lifts[l]);
            double bottom = dm_tablet_pad_y(m, DM_TABLET_FACE_Y - DM_TABLET_FACE_GAP - DM_TABLET_FACE_R * 1.6);
            double top = dm_tablet_pad_y(m, DM_TABLET_SHOULDER_Y + DM_TABLET_SHOULDER_R * 1.35);
            double inner = (DM_TABLET_CLICK_X + DM_TABLET_CLICK_R * 1.35) * m.scale;
            if (bottom <= 0 || top >= height || inner >= width / 2) return 33;
            if (fabs(dm_tablet_pad_y(m, DM_TABLET_STICK_Y) - height / 2 - lifts[l] * m.scale) > 0.001) return 34;
        }
    }
    return 0;
}
#else
int main(void) { return 30; } /* No tablet layout to render or hit-test. */
#endif
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            c, exe = root / 'tablet.c', root / 'tablet.exe'
            c.write_text(source)
            build = subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-I',
                                    str(REPO / 'dm/ios/Sources'), str(c), '-o', str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            status = subprocess.run([str(exe)]).returncode
            self.assertNotEqual(status, 35, 'Both tablet sticks must be centred vertically by default')
            self.assertEqual(status, 0, 'Tablet layout is missing or has out-of-bounds/overlapping hit regions')

    def test_touch_only_start_and_hidden_switch(self):
        source='''#include "TouchLayoutPolicy.h"
int main(void) {
 if(dm_initial_pad_layout(2,0,1,1,1)!=2) return 10;
 if(dm_layout_switch_visible(1,1)!=0) return 11;
 if(dm_initial_pad_layout(0,1,1,1,0)!=1) return 12;
 if(dm_initial_pad_layout(2,0,0,0,1)!=0) return 13;
 if(dm_layout_switch_visible(1,0)!=1) return 14;
 if(dm_layout_switch_visible(0,1)!=1) return 15;
 return 0;
}'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);c=root/'policy.c';exe=root/'policy.exe';c.write_text(source)
            build=subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I',str(REPO/'dm/ios/Sources'),str(c),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(exe)])
            self.assertEqual(run.returncode,0,'10: saved 2D overrides touch-only; 11: Tap switch remains visible')
if __name__=='__main__':unittest.main()
