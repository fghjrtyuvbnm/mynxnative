"""Encrypt locally prepared ZeldaBreathOfTheWild modules and static shader inputs."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from ipa_crypto import transform

TITLE = '01007EF00011E000'
WORK = Path(Path('local-private/botw-work.txt').read_text(encoding='utf-8-sig').strip())
MARKER = 'Pack/Bootup_Graphics.pack'

def main():
    work = WORK
    out = work/'external-build'
    out.mkdir(exist_ok=True)
    ex = work/'extract/v786432'
    romfs = ex/'RomFS'
    aoc = work/'aoc'
    if not romfs.is_dir(): romfs = work/'ZeldaBreathOfTheWild-Data/romfs'
    if not romfs.is_dir() and (work/'ZeldaBreathOfTheWild-Data/romfs.img').is_file():
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dm/tools'))
        import romfs as image_reader
        romfs=image_reader.Path(work/'ZeldaBreathOfTheWild-Data/romfs.img')
    if not aoc.is_dir(): aoc = work/'ZeldaBreathOfTheWild-Data/aoc'
    files = []
    facts = json.loads((work/'preparation.json').read_text())
    for folder,prefix in ((romfs,'romfs'),(aoc,'aoc')):
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream,'sha256').hexdigest()
                files.append(dict(path=prefix+'/'+path.relative_to(folder).as_posix(),size=path.stat().st_size,sha256=digest))
    if sum(f['path'].startswith('romfs/') for f in files) != facts['resource_count'] or len(facts['dlc']) != 2:
        raise ValueError('Incomplete merged Breath of the Wild resources')
    if not (romfs/MARKER).is_file() or not all((aoc/f'{i}.img').is_file() for i in (1,2)):
        raise ValueError('Missing required game data or DLC')
    raw = json.dumps(files,separators=(',',':')).encode()
    (out/'game-assets.json').write_bytes(raw)
    archive = out/'prepared.tar.xz'
    with tarfile.open(archive,'w:xz',preset=3) as tar:
        def bytes_at(name,payload):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            tar.addfile(member,io.BytesIO(payload))
        bytes_at('game-assets.json',raw)
        tar.add(work/'preparation.json','preparation.json',recursive=False)
        for path in sorted((work/'profile'/TITLE).iterdir()):
            if path.is_file():
                payload = path.read_bytes()
                if path.name == 'game.tsv':
                    lines = payload.decode().splitlines()
                    lines = ['romfs_marker\t'+MARKER if line.startswith('romfs_marker\t') else line for line in lines]
                    payload = ('\n'.join(lines)+'\n').encode()
                bytes_at('profile/'+TITLE+'/'+path.name,payload)
        for path in sorted((work/'patched_v786432').iterdir()):
            if path.is_file() and path.suffix in ('.bin','.tsv'):
                tar.add(path,'patched_v786432/'+path.name,recursive=False)
        for name in ('control.nacp','icon.jpg','ExeFS/main.npdm'):
            tar.add(ex/name,'extract/v786432/'+name,recursive=False)
        for path in sorted((work/'shader/pkg').iterdir()):
            if path.is_file():
                tar.add(path,'shader/pkg/'+path.name,recursive=False)
        pairs = work/'shader/pso_pairs.tsv'
        if not pairs.is_file():
            pairs = work/'profile'/TITLE/'pso_pairs.tsv'
        tar.add(pairs,'shader/pso_pairs.tsv',recursive=False)
        # Only an existence marker is needed by Xcode preparation; full data stays local.
        with (romfs/MARKER).open('rb') as stream:
            bytes_at('extract/v786432/RomFS/'+MARKER,stream.read(4096))
    transform(archive,out/'prepared.tar.xz.enc',bytes.fromhex(Path('local-private/build.key').read_text().strip()))
    print('Verified local resources:',len(files),sum(f['size'] for f in files),flush=True)
    print('Encrypted build inputs:',(out/'prepared.tar.xz.enc').stat().st_size,flush=True)

if __name__ == '__main__':
    main()
