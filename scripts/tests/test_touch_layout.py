"""Exercise the same C layout policy called by the UIKit frontend."""
from pathlib import Path
import subprocess,tempfile,unittest
REPO=Path(__file__).resolve().parents[2]
class TouchLayout(unittest.TestCase):
    def test_tablet_controls_fit_mini_and_smaller_windows(self):
        source = '''#if __has_include("TabletPadLayout.h")
#include "TabletPadLayout.h"
#include <math.h>

static int fits(double width, double height) {
    double scale = dm_tablet_pad_scale(width, height);
    double stickGrab = DM_TABLET_STICK_R * DM_TABLET_STICK_GRAB;
    double faceGrab = DM_TABLET_FACE_GAP + DM_TABLET_FACE_R * 1.6;
    if (DM_TABLET_STICK_X <= stickGrab || DM_TABLET_STICK_Y <= stickGrab) return 1;
    if (hypot(DM_TABLET_FACE_X-DM_TABLET_STICK_X, DM_TABLET_FACE_Y-DM_TABLET_STICK_Y) <= faceGrab+stickGrab) return 2;
    if (DM_TABLET_SHOULDER_Y * scale >= height * 0.6) return 3;
    if ((DM_TABLET_MENU_X + DM_TABLET_MENU_W / 2 + 8) * scale >= width / 2) return 4;
    if (DM_TABLET_CLICK_X-DM_TABLET_STICK_X <= stickGrab + DM_TABLET_CLICK_R * 1.35) return 5;
    if (DM_TABLET_SHOULDER_IN_X-DM_TABLET_SHOULDER_OUT_X <= DM_TABLET_SHOULDER_R * 2.7) return 6;
    return 0;
}

int main(void) {
    if (fits(1133, 720)) return fits(1133, 720);
    if (fits(600, 420)) return fits(600, 420) + 10;
    if (DM_TABLET_FACE_R * dm_tablet_pad_scale(1133, 720) * 2 < 44) return 20;
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
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0,
                             'Tablet layout is missing or has out-of-bounds/overlapping hit regions')

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
