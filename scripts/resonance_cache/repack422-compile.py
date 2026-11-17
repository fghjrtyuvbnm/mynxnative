"""Build two external-data IPAs with the upstream iOS host."""
import hashlib
import json
import importlib
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile

SOURCE='422ec2409500da4637294b8b0ab0811755f214d4'
CHAIN='13b3bdb97e7e'
APP='Payload/DmIOS.app/'
GAMES={
    'three-houses':('010055D009F78000','v327680','1.2.0','89048449ba238c8cf565518b83bf02d3','Fire Emblem Three Houses','DATA1.bin','en-US'),
    'triangle':('0100CC80140F8000','v262144','1.1.1','9cb4490e8a718bae392c59b0368d7c4e','TRIANGLE STRATEGY','Newera/Content/Paks/Newera-Switch.pak','zh-Hans'),
}

def rows(path):
    return [line.split(chr(9),4) for line in path.read_text().splitlines()
            if line and not line.startswith(('#','package'+chr(9)))]

def validate_shader_packages(shader, expected):
    import shader_split
    groups={}
    for name,index,stage,key,_ in expected:
        groups.setdefault(name,{})[int(index)]=key
    for name, entries in groups.items():
        path=shader/'pkg'/name
        with path.open('rb') as stream:
            records=stream.read().split(b'BTCDBTCD')
        assert records.pop(0)==b'' and len(records)==len(entries)
        updated=path.with_suffix('.pending')
        with updated.open('wb') as out:
            for index,record in enumerate(records):
                key=entries[index]
                ctl_size,code_size=struct.unpack_from('<2I',record,0x20)
                code,ctl=record[0x30:0x30+code_size],record[0x30+code_size:]
                assert len(ctl)==ctl_size and shader_split.skey(ctl,code)==key
                assert record[:8] in (bytes(8),bytes.fromhex(key))
                out.write(b'BTCDBTCD'+bytes.fromhex(key)+record[8:])
        updated.replace(path)

def main(repo, archive, original, work, out, name):
    repo, archive, original, work, out=(Path(p).resolve() for p in (repo,archive,original,work,out))
    assert subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip()==SOURCE
    title, version, display_version, main_build, display, marker, lang=GAMES[name]
    work.mkdir()
    out.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(work,filter='data')
    shader=work/'shader'
    profile=repo/'dm/games'/title
    if name=='triangle':
        old=work/'old-input'
        old.mkdir()
        with tarfile.open(original) as stream:
            paths=[e for e in stream if e.isfile() and e.name.startswith('local-shaders/')]
            stream.extractall(old,members=paths,filter='data')
        old=old/'local-shaders'
        assert [x[:4] for x in rows(old/'shader_map.tsv')]==[x[:4] for x in rows(profile/'shader_map.tsv')]
        shutil.copytree(old/'pkg',shader/'pkg')
        shutil.copyfile(old/'pso_pairs.tsv',shader/'pso_pairs.tsv')
    os.environ.update(GAME=title,DM_GAME=title)
    sys.path[:0]=[str(repo/p) for p in ('scripts','dm/tools','dm/games','dm/gfx/tools')]
    build=importlib.import_module('build_ipa_from_nsp')
    g=importlib.import_module('game').load(title)
    build.PROG.mode='lines'; build.PROG.plan(3)
    logs=work/'logs'; logs.mkdir()
    (work/'tmp').mkdir()
    env=dict(os.environ, J='6', WORK=str(work/'tmp'), DM_ROOT=str(work))
    assert build.chain_of(repo)==CHAIN
    patched=work/f'patched_{version}'
    assert main_build in (patched/'main.fixups.tsv').read_text()
    validate_shader_packages(shader,rows(profile/'shader_map.tsv'))
    ios=build.build_shaders(Path(sys.executable),repo,shader,repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate',env,logs,g,pull=True)
    lib=build.shader_lib.view(ios/f'b-{CHAIN}')
    stamp=dict(line.split(chr(9),1) for line in (lib/'inputs.tsv').read_text().splitlines() if line and not line.startswith('#'))
    manifest={
        'format_version':1,
        'identity':dict(title_id=title,main_build=main_build,shader_chain=CHAIN,shader_inputs=stamp['inputs']),
        'files':json.loads((work/'game-assets.json').read_text()),
    }
    with (out/'shaders.pack').open('xb') as stream:
        stream.write(b'FFRSMSL1')
        files=sorted((p for p in lib.iterdir() if p.suffix in ('.json','.metallib','.tsv')),key=lambda p:p.name)
        assert any(p.suffix=='.metallib' for p in files)
        names={p.name for p in files}
        for _,_,stage,key,_ in rows(profile/'shader_map.tsv'):
            if f'{key}_b.metallib' not in names:
                meta=json.loads((lib/f'{key}_b.json').read_text())
                if stage!='geometry' or 'gs_slice' not in meta:
                    raise ValueError('Missing translated shader '+key)
        for p in files:
            payload=p.read_bytes()
            stream.write(payload)
            manifest['files'].append(dict(path=f'msl/b-{CHAIN}/{p.name}',size=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    raw=json.dumps(manifest,separators=(',',':')).encode()
    (out/'game-data.json').write_bytes(raw)
    extract=work/'extract'/version
    derived=work/'xcode-dd'
    bundle='org.nxnative.'+title.lower()
    env.update(W=str(work/'ipa'),PATCHED=str(patched),ROMFS=str(extract/'RomFS'),MSL_IOS=str(ios),
               GFXAPI='nvn',FONT_PY=sys.executable,DM_DISPLAY_NAME=display,DM_BUNDLE_ID=bundle,DM_APP_VERSION=display_version,
               DM_LANG=lang,DM_PSO_GPUS='none',DM_ENTITLEMENTS='',DM_ICON=str(extract/'icon.jpg'),AOC='',
               DM_COPY_ROMFS='NO',DM_XCODE_DERIVED_DATA=str(derived))
    def run(*args):
        subprocess.run([str(p) for p in args],env=env,check=True)
    run('bash',repo/'dm/ios/tools/build_ipa.sh','--prepare-xcode')
    project=work/'ipa/xcode'
    plist=project/'Gen/Info.plist'
    info=plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True,DMExternalDataVersion=1,DMLocalDataManagement=True,
                DMExternalDataIdentity=manifest['identity'],DMExternalRomFSMarker=marker,
                DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),LSSupportsOpeningDocumentsInPlace=True,UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{display} ({title})',
        '-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',derived,
        'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(derived),'SYMROOT='+str(derived/'Build/Products'),
        'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
    ipa=out/'game.ipa'
    skip=[item for n in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for item in ('--skip',APP+n)]
    run(sys.executable,repo/'dm/ios/tools/pack_ipa.py',ipa,*skip,APP.rstrip('/')+'='+str(derived/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(ipa) as z:
        info=plistlib.loads(z.read(APP+'Info.plist'))
        assert z.testzip() is None and info['DTSDKName']=='iphoneos27.2' and info['CFBundleIdentifier']==bundle
        assert info['DMExternalDataIdentity']==manifest['identity']
    build.PROG.close()

if __name__=='__main__':
    main(*sys.argv[1:])
