"""Build the separated Disco Elysium package against the pinned upstream source."""
from pathlib import Path
import hashlib
import importlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

SOURCE = 'e6a358f5c1311c5a320e749a7ce3ddfd60ae1c7b'
CHAIN = '53cf95b181aa'
TITLE = '01006C5015E84000'
MAIN = '7c463c12553bab2d98dd6d579d60af07'
APP = 'Payload/DmIOS.app/'
MARKER = 'Data/AmplifyTexture/0d06445cc08e1d1a9a28ab04e56a8e48.vtc2_nx'
DISPLAY = 'Disco Elysium - The Final Cut'


def main(repo, archive, work, out):
    repo, archive, work, out = (Path(p).resolve() for p in (repo, archive, work, out))
    if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE:
        raise ValueError('Unexpected upstream source')
    work.mkdir()
    out.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(work, filter='data')
    logs = work/'logs'
    logs.mkdir()
    (work/'tmp').mkdir()
    sys.path[:0] = [str(repo/'scripts'), str(repo/'dm/tools'), str(repo/'dm/games')]
    os.environ.update(GAME=TITLE, DM_GAME=TITLE, DM_GAMES_DIR=str(work/'profile'))
    build = importlib.import_module('build_ipa_from_nsp')
    game = importlib.import_module('game').load(TITLE)
    build.PROG.mode = 'lines'
    build.PROG.plan(4)
    env = dict(os.environ, J='6', WORK=str(work/'tmp'), DM_ROOT=str(work))
    if build.chain_of(repo) != CHAIN:
        raise ValueError('Unexpected shader chain')
    patched = work/'patched_v851968'
    if f'# BUILD_ID\t{MAIN}\n' not in (patched/'main.fixups.tsv').read_text():
        raise ValueError('Unexpected rewritten executable')
    import profile_guess
    build.pg = profile_guess
    build.provisional_prep(Path(sys.executable), repo, env, logs, game)
    game = build.heap_check(repo, work/'extract', patched, work, env, logs, game)
    shader = work/'shader'
    ios = build.build_shaders(Path(sys.executable), repo, shader,
                              repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate', env, logs, game, pull=True)
    lib = build.shader_lib.view(ios/f'b-{CHAIN}')
    stamp = dict(line.split('\t',1) for line in (lib/'inputs.tsv').read_text().splitlines()
                 if line and not line.startswith('#'))
    manifest = {
        'format_version': 1,
        'identity': dict(title_id=TITLE, main_build=MAIN, shader_chain=CHAIN, shader_inputs=stamp['inputs']),
        'files': json.loads((work/'game-assets.json').read_text()),
    }
    with (out/'shaders.pack').open('xb') as stream:
        stream.write(b'FFRSMSL1')
        files = sorted((p for p in lib.iterdir() if p.suffix in ('.json','.metallib','.tsv')), key=lambda p: p.name)
        if not any(p.suffix == '.metallib' for p in files):
            raise ValueError('No iOS shader libraries')
        for p in files:
            payload = p.read_bytes()
            stream.write(payload)
            manifest['files'].append(dict(path=f'msl/b-{CHAIN}/{p.name}', size=len(payload),
                                          sha256=hashlib.sha256(payload).hexdigest()))
    raw = json.dumps(manifest, separators=(',', ':')).encode()
    (out/'game-data.json').write_bytes(raw)
    extract = work/'extract'
    derived = work/'xcode-dd'
    bundle = 'org.nxnative.'+TITLE.lower()
    env.update(W=str(work/'ipa'), PATCHED=str(patched), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_DISPLAY_NAME=DISPLAY, DM_BUNDLE_ID=bundle,
               DM_APP_VERSION='1.0.13', DM_LANG='zh-Hans', DM_PSO_GPUS='none', DM_ENTITLEMENTS='',
               DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO', DM_XCODE_DERIVED_DATA=str(derived))
    def run(*args):
        subprocess.run([str(p) for p in args], env=env, check=True)
    run('bash',repo/'dm/ios/tools/build_ipa.sh','--prepare-xcode')
    project = work/'ipa/xcode'
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1, DMLocalDataManagement=True,
                DMExternalDataIdentity=manifest['identity'], DMExternalRomFSMarker=MARKER,
                DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(), LSSupportsOpeningDocumentsInPlace=True,
                UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{DISPLAY} ({TITLE})',
        '-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',derived,
        'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(derived), 'SYMROOT='+str(derived/'Build/Products'),
        'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
    ipa = out/'DiscoElysiumTheFinalCut.ipa'
    skip = [item for n in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc')
            for item in ('--skip',APP+n)]
    built = derived/'Build/Products/Release-iphoneos/DmIOS.app'
    run(sys.executable,repo/'dm/ios/tools/pack_ipa.py',ipa,*skip,APP.rstrip('/')+'='+str(built))
    with zipfile.ZipFile(ipa) as z:
        info = plistlib.loads(z.read(APP+'Info.plist'))
        executable = z.read(APP+info['CFBundleExecutable'])
        if (z.testzip() or info['DTSDKName'] != 'iphoneos27.2' or info['CFBundleIdentifier'] != bundle
            or any(n.startswith(APP+key) for n in z.namelist() for key in ('romfs','msl/','aoc/'))
            or not executable or not info.get('DMExternalGameData')):
            raise ValueError('Invalid external-data IPA')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
