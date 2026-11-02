"""Exercise the same C layout policy called by the UIKit frontend."""
from pathlib import Path
import subprocess,tempfile,unittest
REPO=Path(__file__).resolve().parents[2]
class TouchLayout(unittest.TestCase):
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
