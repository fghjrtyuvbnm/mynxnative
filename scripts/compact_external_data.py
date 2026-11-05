"""Consolidate external game resources, preserving data and IPA as one contract."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dm/tools'))
import romfs
import romfs_image
from package_policy import patch_ipa


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def consolidate(ipa,data):
    ipa,data=Path(ipa).resolve(),Path(data).resolve()
    manifest_path=data/'game-data.json'
    old=manifest_path.read_bytes();manifest=json.loads(old)
    groups=[]
    if any(r['path'].startswith('romfs/') for r in manifest['files']): groups.append(('romfs/','romfs.img'))
    aoc=data/'aoc'
    if aoc.is_dir():
        for child in sorted(aoc.iterdir()):
            if child.is_dir():
                if not child.name.isdecimal(): raise ValueError('Unexpected DLC directory')
                groups.append(('aoc/'+child.name+'/', 'aoc/'+child.name+'.img'))
    backup_manifest=manifest_path.with_name('game-data.json.precompact')
    backup_ipa=ipa.with_name(ipa.name+'.precompact')
    if backup_manifest.exists() or backup_ipa.exists(): raise ValueError('Previous consolidation needs recovery')
    need=sum(r['size'] for r in manifest['files'] if any(r['path'].startswith(p) for p,_ in groups))
    if shutil.disk_usage(data.parent).free < need+ipa.stat().st_size+512*1024**2:
        raise ValueError('Not enough space to consolidate safely')
    with tempfile.TemporaryDirectory(prefix='.compact-',dir=data.parent) as tmp:
        temp=Path(tmp);images=[]
        for number,(prefix,image_name) in enumerate(groups):
            source=data/prefix.rstrip('/')
            if not source.resolve().is_relative_to(data) or source.is_symlink(): raise ValueError('Unsafe resource directory')
            for entry in source.rglob('*'):
                linked = (bool(entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                          if os.name=='nt' else entry.is_symlink())
                if linked:
                    raise ValueError('Linked game resource')
            image=temp/f'{number}.img'
            print('Consolidating',prefix,flush=True)
            romfs_image.pack(source,image)
            index=romfs_image.read_index(image)
            expected={r['path'][len(prefix):]:r for r in manifest['files'] if r['path'].startswith(prefix)}
            if {n for n,e in index.items() if not e[0]}!=set(expected): raise ValueError('Image resource set differs')
            virtual=romfs.Path(image)
            for name,row in expected.items():
                path=virtual/name
                if path.stat().st_size!=row['size'] or digest(path)!=row['sha256']:
                    raise ValueError('Image resource differs: '+name)
            row=dict(path=image_name,size=image.stat().st_size,sha256=digest(image))
            images.append((image,data/image_name,row,source))
            print('Verified consolidated image:',image_name,len(expected),'resources',flush=True)
        updated=dict(manifest)
        updated['files']=[r for r in manifest['files'] if not any(r['path'].startswith(prefix) for prefix,_ in groups)]
        updated['files'] += [row for _,_,row,_ in images]
        raw=json.dumps(updated,separators=(',',':')).encode()
        new_manifest=temp/'game-data.json';new_manifest.write_bytes(raw)
        new_ipa=temp/'updated.ipa';patch_ipa(ipa,new_ipa,hashlib.sha256(raw).hexdigest())
        installed=[]
        try:
            for image,destination,_,_ in images:
                if destination.exists(): raise FileExistsError(destination)
                destination.parent.mkdir(parents=True,exist_ok=True)
                image.rename(destination);installed.append(destination)
            os.replace(manifest_path,backup_manifest)
            os.replace(new_manifest,manifest_path)
            os.replace(ipa,backup_ipa)
            os.replace(new_ipa,ipa)
        except BaseException:
            # Backups live outside TemporaryDirectory, even if recovery fails.
            try:
                if backup_ipa.exists(): os.replace(backup_ipa,ipa)
                if backup_manifest.exists(): os.replace(backup_manifest,manifest_path)
                for path in installed: path.unlink()
            except OSError as error:
                raise RuntimeError('Consolidation recovery required; original resources and backups preserved') from error
            raise
        backup_manifest.unlink();backup_ipa.unlink()
        # Original packages are outside this data folder. Delete only directories
        # whose complete contents have just matched the verified image.
        for _,_,_,source in images:
            if not source.resolve().is_relative_to(data) or source.resolve()==data: raise ValueError('Unsafe cleanup target')
            shutil.rmtree(source)
    result=dict(ipa=str(ipa),data=str(data),images=[r['path'] for _,_,r,_ in images],
                files=sum(p.is_file() for p in data.rglob('*')),device_gyro_default=True)
    print('Compact external package ready:',json.dumps(result),flush=True)
    return result


if __name__=='__main__': consolidate(*sys.argv[1:])
