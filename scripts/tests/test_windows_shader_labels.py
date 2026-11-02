"""Source labels must preserve upstream POSIX shader groups on Windows."""
import sys,unittest,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import split_windows_shaders as scanner
class SourceLabels(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows path regression')
    def test_bundle_label_uses_portable_separators(self):
        self.assertEqual(scanner.relative_label(r'D:\work\Bundle\data01.impak',r'D:\work'),'Bundle/data01.impak')
if __name__=='__main__':unittest.main()
