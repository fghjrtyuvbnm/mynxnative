"""Verify and install the locally assembled ZeldaBreathOfTheWild external package."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tarfile
import tempfile
import zipfile


def main(work, archive):
    work = Path(work)
    with tempfile.TemporaryDirectory(prefix='botw-output-',dir=work) as name:
        temp = Path(name)
        with tarfile.open(archive) as tar:
            if sorted(tar.getnames()) != ['ZeldaBreathOfTheWild.ipa','game-data.json','shaders.pack']:
                raise ValueError('Unexpected output files')
            tar.extractall(temp, filter='data')
        raw = (temp/'game-data.json').read_bytes()
        data = json.loads(raw)
        local = json.loads((work/'external-build/game-assets.json').read_bytes())
        if [row for row in data['files'] if not row['path'].startswith('msl/')] != local:
            raise ValueError('Cloud manifest does not match the verified local resources')
        with zipfile.ZipFile(temp/'ZeldaBreathOfTheWild.ipa') as z:
            info = plistlib.loads(z.read('Payload/DmIOS.app/Info.plist'))
            if (info['DMShaderCacheManifest'] != hashlib.sha256(raw).hexdigest()
                    or info['DMExternalDataIdentity'] != data['identity'] or z.testzip()):
                raise ValueError('Launcher and data differ')
        target = work/'ZeldaBreathOfTheWild-Data'
        ipa = work/'ZeldaBreathOfTheWild-1.6.0-external-packed-unsigned.ipa'
        if target.exists() or ipa.exists():
            raise FileExistsError('ZeldaBreathOfTheWild output already exists')
        shaders = [row for row in data['files'] if row['path'].startswith('msl/')]
        with (temp/'shaders.pack').open('rb') as stream:
            if stream.read(8) != b'FFRSMSL1':
                raise ValueError('Invalid shader pack header')
            for row in shaders:
                block = stream.read(row['size'])
                if len(block) != row['size'] or hashlib.sha256(block).hexdigest() != row['sha256']:
                    raise ValueError('Shader data differs: '+row['path'])
            if stream.read(1):
                raise ValueError('Unexpected shader pack trailer')
        # Verify every full resource before moving either source directory.
        sources = {'romfs':work/'extract/v786432/RomFS','aoc':work/'aoc'}
        expected = {prefix:set() for prefix in sources}
        for row in local:
            prefix, relative = row['path'].split('/', 1)
            if prefix not in sources or '..' in Path(relative).parts or Path(relative).is_absolute():
                raise ValueError('Unsafe data path')
            src = sources[prefix]/relative
            if not src.resolve().is_relative_to(work.resolve()) or src.is_symlink():
                raise ValueError('Resource outside game work directory')
            if src.stat().st_size != row['size']:
                raise ValueError('Local resource changed: '+row['path'])
            with src.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Local resource hash changed: '+row['path'])
            expected[prefix].add(src.resolve())
        for prefix, source in sources.items():
            if source.is_symlink() or not source.resolve().is_relative_to(work.resolve()):
                raise ValueError('Unsafe source directory')
            actual = {p.resolve() for p in source.rglob('*') if p.is_file()}
            if actual != expected[prefix]:
                raise ValueError('Unmanifested or missing source resources: '+prefix)
        folder = temp/'data'; folder.mkdir()
        for name in ('game-data.json','shaders.pack'):
            (temp/name).rename(folder/name)
        # Keep the destination outside TemporaryDirectory before moving game data:
        # even a failed rollback must leave recoverable data, never delete it.
        if not target.resolve().is_relative_to(work.resolve()):
            raise ValueError('Unsafe destination directory')
        folder.rename(target)
        moved = []
        try:
            for prefix, source in sources.items():
                destination = target/prefix
                source.rename(destination)
                moved.append((source,destination))
            (temp/'ZeldaBreathOfTheWild.ipa').rename(ipa)
        except BaseException:
            failed = []
            for source,destination in reversed(moved):
                try: destination.rename(source)
                except OSError: failed.append(str(destination))
            if failed:
                raise RuntimeError('Assembly rollback incomplete; preserved resources at '+', '.join(failed))
            for name in ('game-data.json','shaders.pack'): (target/name).unlink()
            target.rmdir()
            raise
    from compact_external_data import consolidate
    consolidate(ipa,target)
    print(f'Created {ipa} and {target} with {len(shaders)} verified shader records')


if __name__ == '__main__':
    main(*sys.argv[1:])
