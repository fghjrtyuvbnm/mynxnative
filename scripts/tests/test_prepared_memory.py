"""Prepared cloud inputs must refresh memory cost before Apple compilation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = Path(os.environ.get('NXNATIVE_REPO', Path(__file__).resolve().parents[2]))
TITLE = '0100F0E0136BE000'


class StopBeforeApple(Exception):
    pass


class PreparedMemory(unittest.TestCase):
    def test_old_prepared_profile_covers_large_rewritten_module(self):
        script = Path(os.environ.get('CLOUD_SCRIPT_PATH', REPO / 'scripts/cloud_compile_uncharted.py'))
        spec = importlib.util.spec_from_file_location('cloud_memory_test', script)
        cloud = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cloud)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / 'input'
            profile = data / 'profile' / TITLE
            profile.mkdir(parents=True)
            (profile / 'game.tsv').write_text(f'title_id\t{TITLE}\nmodules\tmain\nsys_resource\t0\n')
            patched = data / 'patched_v131072'
            patched.mkdir()
            (patched / 'main.fixups.tsv').write_text('# PATCH_OFF\t0\n')
            with (patched / 'main.patched.bin').open('wb') as stream:
                stream.truncate(66 * 1024 * 1024)
            files = sorted(p for p in data.rglob('*') if p.is_file())
            rows = []
            for path in files:
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                rows.append({'path': path.relative_to(data).as_posix(), 'sha256': digest})
            manifest = {'title_id': TITLE, 'source': cloud.SOURCE, 'files': rows}
            (data / 'input-manifest.json').write_text(json.dumps(manifest))
            archive = root / 'input.tar.gz'
            with tarfile.open(archive, 'w:gz', compresslevel=1) as package:
                for path in data.rglob('*'):
                    if path.is_file():
                        package.add(path, arcname=path.relative_to(data).as_posix())
            original_spec = importlib.util.spec_from_file_location

            def intercept(name, path, *args, **kwargs):
                target = original_spec(name, path, *args, **kwargs)
                if name == 'nsp_build':
                    original_exec = target.loader.exec_module

                    def load(module):
                        original_exec(module)

                        def check_before_compilation(*unused):
                            updated = (root / 'work/profile' / TITLE / 'game.tsv').read_text()
                            self.assertIn('mem_used\t0x4600000', updated)
                            raise StopBeforeApple()

                        module.check_prereqs = check_before_compilation
                    target.loader.exec_module = load
                return target

            argv = [str(script), str(archive), str(root / 'work'), str(REPO)]
            sys.path.insert(0, str(REPO / 'dm/games'))
            import game
            # The target workflow runs on macOS; adapt its colon-separated roots
            # to a Windows temporary path without changing this memory regression.
            with mock.patch.dict(os.environ), mock.patch.object(sys, 'argv', argv), \
                    mock.patch.object(game, 'extra_dirs', side_effect=lambda: [Path(os.environ['DM_GAMES_DIR'])]), \
                    mock.patch.object(importlib.util, 'spec_from_file_location', side_effect=intercept):
                with self.assertRaises(StopBeforeApple):
                    cloud.main()


if __name__ == '__main__':
    unittest.main()
