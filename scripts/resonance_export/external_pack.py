"""Export a small unsigned launcher plus a self-contained, relocatable data folder."""
import copy
from contextlib import nullcontext
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import stat
import sys
import uuid
import zipfile
from contracts import TITLE, BUILD, check_identity, sha256

APP='Payload/DmIOS.app/'

def check_archive_name(name):
    p=pathlib.PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or '\0' in name:raise ValueError('Unsafe IPA path')
    if name not in ('Payload/','Payload/DmIOS.app/') and not name.startswith(APP):raise ValueError('Unexpected IPA root')

def resource_name(name):
    if name.startswith(APP):
        relative=name[len(APP):]
        if relative.split('/')[0] in ('romfs','msl','aoc'):return relative
    return None

def safe_data_path(name):
    p=pathlib.PurePosixPath(name)
    if name=='romfs.img': return p
    if p.is_absolute() or '..' in p.parts or '.' in p.parts or '\\' in name or ':' in name or not p.parts or p.parts[0] not in ('romfs','msl','aoc'):raise ValueError('Unsafe game data path')
    if p.suffix.lower() in ('.keys','.nsp','.xci','.tik'):raise ValueError('Unexpected original container or key file')
    return p

def reconstruct(download):
    download=pathlib.Path(download);m=json.loads((download/'result-manifest.json').read_text());check_identity(m)
    path=download/'FFR-external-template.ipa'
    if path.exists():
        if sha256(path)!=m['template_sha256']:raise ValueError('Existing template hash differs')
        return path,m
    with path.open('xb') as out:
        for i,row in enumerate(m['parts']):
            if row['path']!=f'template.part{i:03}':raise ValueError('Unexpected result part name')
            p=download/row['path']
            if p.stat().st_size!=row['bytes'] or sha256(p)!=row['sha256']:raise ValueError('Result part mismatch')
            with p.open('rb') as f:shutil.copyfileobj(f,out,8*1024*1024)
    if sha256(path)!=m['template_sha256']:raise ValueError('Compiled template mismatch')
    return path,m

def verify_data(root,identity):
    root=pathlib.Path(root);m=json.loads((root/'game-data.json').read_text())
    if m.get('format_version')!=1 or m.get('identity')!=identity:raise ValueError('Existing data folder belongs to another build')
    seen=set();packed=root/'shaders.pack';stamp_bytes=None
    stamp='msl/b-'+identity['shader_chain']+'/inputs.tsv'
    with packed.open('rb') if packed.is_file() else nullcontext(None) as stream:
        if stream is not None and stream.read(8)!=b'FFRSMSL1': raise ValueError('Invalid shader pack')
        for row in m['files']:
            relative=str(safe_data_path(row['path']));p=root/relative
            if relative in seen: raise ValueError('Duplicate game data path')
            if stream is not None and relative.startswith('msl/'):
                raw=stream.read(row['size'])
                if len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Packed shader differs: '+relative)
                if relative==stamp: stamp_bytes=raw
            elif p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or p.stat().st_size!=row['size'] or sha256(p)!=row['sha256']:
                raise ValueError('Game data file differs: '+relative)
            seen.add(relative)
        if stream is not None and stream.read(1):raise ValueError('Trailing shader bytes')
    marker='romfs/FFRS/Content/Paks/FFRS-Switch.ucas';stamp='msl/b-'+identity['shader_chain']+'/inputs.tsv'
    if 'romfs.img' in seen:
        sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'dm/tools'))
        import romfs
        if not (romfs.Path(root/'romfs.img')/marker[6:]).is_file():raise ValueError('Image marker missing')
    elif marker not in seen:raise ValueError('Game data folder is incomplete')
    if stamp not in seen:raise ValueError('Shader stamp missing')
    lines=set((stamp_bytes.decode() if stamp_bytes is not None else (root/stamp).read_text()).splitlines())
    if 'game\t'+identity['title_id'] not in lines or 'inputs\t'+identity['shader_inputs'] not in lines:raise ValueError('Shader stamp differs from game data identity')
    return m

def finish_external(download,work,out):
    download=pathlib.Path(download);work=pathlib.Path(work);out=pathlib.Path(out)
    if out.exists():raise FileExistsError(out)
    template,result=reconstruct(download)
    if not result.get('external_data_runtime'):raise ValueError('This template predates external folder support')
    with zipfile.ZipFile(template) as z:
        entries=z.infolist();seen=set()
        for entry in entries:
            check_archive_name(entry.filename)
            if entry.filename.casefold() in seen:raise ValueError('Duplicate or case-colliding IPA entry')
            seen.add(entry.filename.casefold())
            if stat.S_ISLNK(entry.external_attr>>16) or entry.flag_bits&1:raise ValueError('IPA links and encryption are unsupported')
            if '/_CodeSignature/' in entry.filename or entry.filename.endswith('/embedded.mobileprovision'):raise ValueError('Template unexpectedly contains signing files')
        info=plistlib.loads(z.read(APP+'Info.plist'))
        identity=info.get('DMExternalDataIdentity')
        if info.get('DMExternalGameData') is not True or info.get('DMExternalDataVersion')!=1 or not isinstance(identity,dict):raise ValueError('External data runtime metadata missing')
        check_identity(identity)
        if info.get('CFBundleIdentifier')!='org.nxnative.'+TITLE.lower() or APP+info['CFBundleExecutable'] not in z.namelist():raise ValueError('Wrong launcher executable or bundle')
        if z.testzip():raise ValueError('Template ZIP CRC failed')
        data=out.parent/'FFRS-Data'
        if data.exists():verify_data(data,identity)
        else:
            staging=data.with_name(data.name+'.preparing-'+uuid.uuid4().hex);staging.mkdir()
            files=[]
            for entry in entries:
                relative=resource_name(entry.filename)
                if relative is None or entry.is_dir():continue
                safe_data_path(relative)
                if relative.startswith('romfs/'):raise ValueError('Cloud template must not contain a partial RomFS')
                p=staging/relative;p.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256()
                with z.open(entry) as src,p.open('xb') as dst:
                    for block in iter(lambda:src.read(8*1024*1024),b''):dst.write(block);h.update(block)
                files.append({'path':relative,'size':p.stat().st_size,'sha256':h.hexdigest()})
            romfs=work/'extract/v1/RomFS'
            if not (romfs/'FFRS/Content/Paks/FFRS-Switch.ucas').is_file():raise ValueError('Complete local RomFS missing')
            for p in sorted(romfs.rglob('*')):
                if p.is_symlink():raise ValueError('RomFS symlink unsupported')
                if not p.is_file():continue
                relative='romfs/'+p.relative_to(romfs).as_posix();safe_data_path(relative);target=staging/relative;target.parent.mkdir(parents=True,exist_ok=True)
                print('Exporting local game resource: '+p.name,flush=True)
                try:os.link(p,target) # Independent file entry on NTFS; copying to USB carries the actual bytes.
                except OSError:shutil.copyfile(p,target)
                files.append({'path':relative,'size':target.stat().st_size,'sha256':sha256(target)})
            manifest={'format_version':1,'identity':identity,'files':sorted(files,key=lambda r:r['path'])}
            (staging/'game-data.json').write_text(json.dumps(manifest,separators=(',',':')),encoding='utf-8')
            verify_data(staging,identity)
            if data.exists():raise FileExistsError(data)
            staging.rename(data)
        tmp=out.with_name(out.name+'.partial-'+uuid.uuid4().hex)
        with zipfile.ZipFile(tmp,'x',allowZip64=True,compression=zipfile.ZIP_DEFLATED,compresslevel=1) as destination:
            for entry in entries:
                if resource_name(entry.filename) is not None:continue
                with z.open(entry) as src,destination.open(copy.copy(entry),'w',force_zip64=True) as dst:shutil.copyfileobj(src,dst,8*1024*1024)
        with zipfile.ZipFile(tmp) as launcher:
            if launcher.testzip() or any(resource_name(n) is not None for n in launcher.namelist()):raise ValueError('Launcher split verification failed')
        tmp.rename(out)
    # Keep the public launcher/data contract and the final on-disk layout together.
    from compact_external_data import consolidate
    consolidate(out,data)
    report={'title_id':TITLE,'main_build':BUILD,'signed':False,'data_separate':True,'external_data_runtime':True,'launcher_bytes':out.stat().st_size,
            'launcher_sha256':sha256(out),'data_folder':str(data),'data_files':len(json.loads((data/'game-data.json').read_text())['files']),
            'data_sha256_verified':True,'zip_crc_verified':True,'physical_usb_runtime_tested':False,'gameplay_tested':False}
    out.with_suffix('.verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Unsigned launcher: '+str(out),flush=True);print('Copy this complete folder to the external drive: '+str(data),flush=True)
    return report
