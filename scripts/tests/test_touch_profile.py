"""The same generated profile must drive handheld runtime and launcher defaults."""
from pathlib import Path
import importlib.util,sys,tempfile,unittest,subprocess
REPO=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(REPO/'scripts'),str(REPO/'dm/games')]
import touch_build,game,settings
class TouchProfile(unittest.TestCase):
    def test_compiled_and_launcher_defaults_agree(self):
        spec=importlib.util.spec_from_file_location('touch_nsp',REPO/'scripts/build_ipa_from_nsp.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(dir=REPO/'local-private') as temp:
            p=Path(temp)/'010016100A186000';p.mkdir();(p/'game.tsv').write_text((REPO/'dm/games/010016100A186000/game.tsv').read_text())
            profile=touch_build.configure_profile(builder,game.load(str(p)))
            h=game.header(profile)
            self.assertIn('#define DM_GAME_OPMODE 0\n',h)
            self.assertIn('#define DM_GAME_PAD_LAYOUT 2\n',h)
            patched=p/'patched';patched.mkdir();(patched/'main.fixups.tsv').write_text('')
            rows=settings.build(str(p),patched,p/'control.nacp')
            self.assertEqual(next(r for r in rows['settings'] if r['env']=='DM_OPMODE')['default'],'0')

    def test_source_overlay_is_verified_and_idempotent(self):
        original=subprocess.run(['git','-c','safe.directory='+REPO.as_posix(),'show','cde88f62068e3d879b083b1a86a7fd78610c7b7b:dm/ios/Sources/DmGamepad.m'],capture_output=True,check=True).stdout
        with tempfile.TemporaryDirectory(dir=REPO/'local-private') as temp:
            root=Path(temp);src=root/'dm/ios/Sources';src.mkdir(parents=True)
            ui=src/'DmGamepad.m';ui.write_bytes(original)
            project=root/'dm/ios/project.yml';project.write_text('        DMLanguage: en-US\n')
            touch_build.patch_ios_source(root)
            touch_build.patch_ios_source(root)
            self.assertEqual(touch_build.normalized_sha(ui),touch_build.NEW_UI_SHA)
            self.assertTrue((src/'TouchLayoutPolicy.h').is_file())
            self.assertEqual(project.read_text().count('DMTouchOnly: true'),1)
            ui.write_bytes(b'unexpected source')
            with self.assertRaises(ValueError):touch_build.patch_ios_source(root)
if __name__=='__main__':unittest.main()
