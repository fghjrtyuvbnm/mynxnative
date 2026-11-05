"""Verify and install the locally assembled ASTLIBRA Revision external package."""
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
    with tempfile.TemporaryDirectory(prefix='astlibra-output-',dir=work) as name:
        temp = Path(name)
        with tarfile.open(archive) as tar:
            if sorted(tar.getnames()) != ['AstlibraRevision.ipa','game-data.json','shaders.pack']:
                raise ValueError('Unexpected output files')
            tar.extractall(temp, filter='data')
        raw = (temp/'game-data.json').read_bytes()
        data = json.loads(raw)
        local = json.loads((work/'external-build/game-assets.json').read_bytes())
        if [row for row in data['files'] if not row['path'].startswith('msl/')] != local:
            raise ValueError('Cloud manifest does not match the verified local resources')
        with zipfile.ZipFile(temp/'AstlibraRevision.ipa') as z:
            info = plistlib.loads(z.read('Payload/DmIOS.app/Info.plist'))
            if (info['DMShaderCacheManifest'] != hashlib.sha256(raw).hexdigest()
                    or info['DMExternalDataIdentity'] != data['identity'] or z.testzip()):
                raise ValueError('Launcher and data differ')
        target = work/'AstlibraRevision-Data'
        ipa = work/'AstlibraRevision-1.0.7-external-packed-unsigned.ipa'
        if target.exists() or ipa.exists():
            raise FileExistsError('ASTLIBRA Revision output already exists')
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
        folder = temp/'data'; folder.mkdir()
        for row in local:
            prefix, relative = row['path'].split('/', 1)
            if prefix not in ('romfs','aoc') or '..' in Path(relative).parts or Path(relative).is_absolute():
                raise ValueError('Unsafe data path')
            src = (work/'extract/v327680/RomFS' if prefix == 'romfs' else work/'aoc') / relative
            dst = folder/row['path']
            if src.stat().st_size != row['size']:
                raise ValueError('Local resource changed: '+row['path'])
            with src.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Local resource hash changed: '+row['path'])
            dst.parent.mkdir(parents=True,exist_ok=True)
            try:
                os.link(src,dst)
            except OSError:
                shutil.copy2(src,dst)
        for name in ('game-data.json','shaders.pack'):
            (temp/name).rename(folder/name)
        folder.rename(target)
        (temp/'AstlibraRevision.ipa').rename(ipa)
    from compact_external_data import consolidate
    consolidate(ipa,target)
    print(f'Created {ipa} and {target} with {len(shaders)} verified shader records')


if __name__ == '__main__':
    main(*sys.argv[1:])
