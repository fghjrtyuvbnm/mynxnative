"""Compile a build-matched external-data IPA on the hosted Apple Silicon Mac."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

def main(repo, archive, work, out):
    repo,archive,work,out=map(lambda p:Path(p).resolve(),(repo,archive,work,out))
    work.mkdir(); out.mkdir()
    with tarfile.open(archive) as tar: tar.extractall(work,filter='data')
    state=json.loads((work/'build-state.json').read_bytes())
    title,version,chain=state['title'],state['version'],state['chain']
    # The first local Trails split used Windows' CP936 default for its TSV header.
    # Normalize those captured tables before the UTF-8-only Apple build reads them.
    if state['key']=='trails':
        for folder in (work/'shader',work/'profile'/title):
            for table in folder.glob('*.tsv'):
                raw=table.read_bytes()
                try: raw.decode('utf-8')
                except UnicodeDecodeError:
                    table.write_text(raw.decode('cp936'),encoding='utf-8')
    assert subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip()==state['source_commit']
    profile=repo/'dm/games'/title
    shutil.copytree(work/'profile'/title,profile,dirs_exist_ok=True)
    # Derived profiles with no conflict rulings still need the required table header.
    conflicts=profile/'shader_map.tsv.conflicts.tsv'
    if not conflicts.exists():
        conflicts.write_text('# kind: evidence  control-section key conflict rulings: empty\ndm_ctl_sha16\tchosen_pc\tclass\tcandidates\trecords\n')
    os.environ.update(GAME=title,DM_GAME=title)
    sys.path[:0]=[str(repo/p) for p in ('scripts','dm/tools','dm/games','dm/gfx/tools')]
    build=importlib.import_module('build_ipa_from_nsp')
    g=importlib.import_module('game').load(title)
    assert build.chain_of(repo)==chain
    build.PROG.mode='lines'; build.PROG.plan(3)
    logs=work/'logs'; logs.mkdir()
    (work/'tmp').mkdir()
    env=dict(os.environ,J='6',WORK=str(work/'tmp'),DM_ROOT=str(work))
    patched=work/('patched_'+version)
    assert state['main_build'] in (patched/'main.fixups.tsv').read_text()
    ios=build.build_shaders(Path(sys.executable),repo,work/'shader',repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate',env,logs,g,pull=True)
    lib=build.shader_lib.view(ios/('b-'+chain))
    stamp=dict(l.split(chr(9),1) for l in (lib/'inputs.tsv').read_text().splitlines() if l and not l.startswith('#'))
    manifest=dict(format_version=1,identity=dict(title_id=title,main_build=state['main_build'],shader_chain=chain,shader_inputs=stamp['inputs']),files=json.loads((work/'game-assets.json').read_bytes()))
    with (out/'shaders.pack').open('xb') as stream:
        stream.write(b'FFRSMSL1')
        files=sorted((p for p in lib.iterdir() if p.suffix in ('.json','.metallib','.tsv')),key=lambda p:p.name)
        assert any(p.suffix=='.metallib' for p in files)
        for p in files:
            raw=p.read_bytes(); stream.write(raw)
            manifest['files'].append(dict(path='msl/b-'+chain+'/'+p.name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    raw=json.dumps(manifest,separators=(',',':')).encode()
    (out/'game-data.json').write_bytes(raw)
    ex=work/'extract'/version; derived=work/'xcode-dd'
    display='DRAGON QUEST VII' if state['key']=='dq7' else 'Trails in the Sky 1st'
    bundle='org.nxnative.'+title.lower()
    # Bundle versions accept only three numeric fields; the game release stays in build-state.
    app_version='1.2.0' if state['key']=='dq7' else '1.0.6'
    env.update(W=str(work/'ipa'),PATCHED=str(patched),ROMFS=str(ex/'RomFS'),MSL_IOS=str(ios),
               GFXAPI='nvn',FONT_PY=sys.executable,DM_DISPLAY_NAME=display,DM_BUNDLE_ID=bundle,DM_APP_VERSION=app_version,
               DM_LANG='zh-Hans',DM_PSO_GPUS='none',DM_ENTITLEMENTS='',DM_ICON=str(ex/'icon.jpg'),AOC='',
               DM_COPY_ROMFS='NO',DM_XCODE_DERIVED_DATA=str(derived))
    def run(*args): subprocess.run(list(map(str,args)),env=env,check=True)
    run('bash',repo/'dm/ios/tools/build_ipa.sh','--prepare-xcode')
    project=work/'ipa/xcode'; plist=project/'Gen/Info.plist'
    info=plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True,DMExternalDataVersion=1,DMLocalDataManagement=True,
                DMExternalDataIdentity=manifest['identity'],DMExternalRomFSMarker=state['marker'],
                DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),LSSupportsOpeningDocumentsInPlace=True,UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',display+' ('+title+')',
        '-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',derived,
        'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(derived),'SYMROOT='+str(derived/'Build/Products'),
        'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
    app='Payload/DmIOS.app/'
    skip=[x for n in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for x in ('--skip',app+n)]
    run(sys.executable,repo/'dm/ios/tools/pack_ipa.py',out/'game.ipa',*skip,app.rstrip('/')+'='+str(derived/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(out/'game.ipa') as z:
        info=plistlib.loads(z.read(app+'Info.plist'))
        assert z.testzip() is None and info['DTSDKName']=='iphoneos27.2' and info['CFBundleIdentifier']==bundle
        assert info['DMExternalDataIdentity']==manifest['identity']
    build.PROG.close()

if __name__=='__main__': main(*sys.argv[1:])
