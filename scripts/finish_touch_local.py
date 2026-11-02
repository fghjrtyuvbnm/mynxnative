"""Rebuild a touch-only IPA with verified resources from a known-good local IPA."""
from pathlib import Path,PurePosixPath
import hashlib,json,plistlib,shutil,struct,zipfile
from ipa_crypto import transform
from touch_build import verify_template
ROOT='Payload/DmIOS.app/'

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def finish(encrypted, donor, keyfile, output):
    donor,output=Path(donor).resolve(),Path(output).resolve()
    if output.exists() or output.with_suffix('.ipa.partial').exists():raise ValueError('Output exists')
    prior=json.loads(donor.with_suffix('.verification.json').read_text())
    if digest(donor)!=prior['sha256']:raise ValueError('Original IPA no longer matches its verification report')
    template=output.parent/'touch-only-template.ipa'
    transform(encrypted,template,bytes.fromhex(Path(keyfile).read_text().strip()),True)
    verify_template(template)
    partial=output.with_suffix('.ipa.partial')
    resources={}
    with zipfile.ZipFile(template) as source,zipfile.ZipFile(donor) as old,zipfile.ZipFile(partial,'w',allowZip64=True) as dest:
        if source.testzip() is not None:raise ValueError('Template CRC mismatch')
        info=plistlib.loads(source.read(ROOT+'Info.plist'))
        old_info=plistlib.loads(old.read(ROOT+'Info.plist'))
        for key in ['CFBundleIdentifier','CFBundleShortVersionString']:
            if info[key]!=old_info[key]:raise ValueError('Template identity differs from original IPA')
        executable=ROOT+info['CFBundleExecutable']
        with source.open(executable) as binary:header=binary.read(8)
        if struct.unpack('<II',header)!=(0xfeedfacf,0x0100000c):raise ValueError('Not arm64')
        for archive,resource_only in [(source,False),(old,True)]:
            for entry in archive.infolist():
                path=PurePosixPath(entry.filename)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe ZIP entry')
                is_resource=entry.filename.startswith((ROOT+'romfs/',ROOT+'aoc/'))
                if is_resource!=resource_only or entry.filename in (ROOT+'romfs.img',ROOT+'romfs.id'):continue
                if resource_only and not entry.is_dir():resources[entry.filename]=entry.file_size
                if entry.is_dir():dest.writestr(entry,b'');continue
                with archive.open(entry) as incoming,dest.open(entry,'w',force_zip64=entry.file_size>=2**31) as outgoing:
                    shutil.copyfileobj(incoming,outgoing,8*1024*1024)
    with zipfile.ZipFile(partial) as final:
        if final.testzip() is not None:raise ValueError('Final CRC mismatch')
        names=final.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP paths')
        if not(final.getinfo(executable).external_attr>>16)&0o111:raise ValueError('Executable mode lost')
        actual={i.filename:i.file_size for i in final.infolist() if i.filename.startswith((ROOT+'romfs/',ROOT+'aoc/')) and not i.is_dir()}
        if actual!=resources or not resources:raise ValueError('Resources incomplete')
    partial.rename(output)
    report=dict(prior,bytes=output.stat().st_size,sha256=digest(output),touch_only=True,
                operation_mode='handheld',pad_layout='touch',layout_button_visible=False,
                zip_crc_verified=True,device_runtime_tested=False,resource_donor_sha256=prior['sha256'])
    output.with_suffix('.verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'file':str(output),'bytes':report['bytes'],'sha256':report['sha256'],'resources':len(resources),'touch_only':True}),flush=True)
