"""Build the separated 1.9.0 package against the pinned upstream source."""
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

SOURCE = 'ee998ae6d73d5960671ec837ea2ae4a8a0489fec'
CHAIN = '0724088d3779'
TITLE = '01007EF00011E000'
MAIN = 'cd57b23fa4bbad65803d9788c01821ee'
APP = 'Payload/DmIOS.app/'
MARKER = 'Pack/Bootup_Graphics.pack'
DISPLAY = 'Zelda Breath of the Wild 1.9.0'


def main(repo, archive, shader_archive, work, out):
    repo, archive, shader_archive, work, out = (Path(p).resolve() for p in (repo, archive, shader_archive, work, out))
    if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE:
        raise ValueError('Unexpected upstream source')
    work.mkdir()
    out.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(work, filter='data')
    with tarfile.open(shader_archive) as stream:
        path = f'profile/{TITLE}/shader_map.tsv'
        previous_map = stream.extractfile(path).read().decode('utf-8')
        current_map = (repo/'dm/games'/TITLE/'shader_map.tsv').read_text()
        packages = [entry for entry in stream if entry.isfile() and entry.name.startswith('shader/pkg/')]
        if not packages: raise ValueError('Missing authenticated shader packages')
        stream.extractall(work, members=packages, filter='data')
    sys.path.insert(0,str(repo/'dm/gfx/tools'))
    from botw_shader_remap import remap
    remap(work/'shader', previous_map, current_map)
    logs = work/'logs'
    logs.mkdir()
    (work/'tmp').mkdir()
    sys.path[:0] = [str(repo/'scripts'), str(repo/'dm/tools'), str(repo/'dm/games')]
    os.environ.update(GAME=TITLE, DM_GAME=TITLE)
    build = importlib.import_module('build_ipa_from_nsp')
    game = importlib.import_module('game').load(TITLE)
    build.PROG.mode = 'lines'
    build.PROG.plan(3)
    env = dict(os.environ, J='6', WORK=str(work/'tmp'), DM_ROOT=str(work))
    if build.chain_of(repo) != CHAIN or game.get('fps_target') != '30':
        raise ValueError('Unexpected shader chain or frame rate')
    patched = work/'patched_v1114112'
    if f'# BUILD_ID\t{MAIN}\n' not in (patched/'main.fixups.tsv').read_text():
        raise ValueError('Unexpected rewritten executable')
    shader = work/'shader'
    ios = build.build_shaders(Path(sys.executable), repo, shader,
                              repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate', env, logs, game, pull=True)
    lib = build.shader_lib.view(ios/f'b-{CHAIN}')
    stamp = dict(line.split('\t',1) for line in (lib/'inputs.tsv').read_text().splitlines()
                 if line and not line.startswith('#'))
    manifest = {
        'format_version': 1,
        'identity': dict(title_id=TITLE, main_build=MAIN, shader_chain=CHAIN, shader_inputs=stamp['inputs']),
        'files': json.loads(Path(__file__).with_name('botw-lite-assets.json').read_text()),
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
    bundle = 'org.nxnative.'+TITLE.lower()+'.v190'
    env.update(W=str(work/'ipa'), PATCHED=str(patched), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_DISPLAY_NAME=DISPLAY, DM_BUNDLE_ID=bundle,
               DM_APP_VERSION='1.9.0', DM_LANG='zh-Hans', DM_PSO_GPUS='none', DM_ENTITLEMENTS='',
               DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO', DM_XCODE_DERIVED_DATA=str(derived))
    def run(*args):
        subprocess.run([str(p) for p in args], env=env, check=True)
    run('bash',repo/'dm/ios/tools/build_ipa.sh','--prepare-xcode')
    project = work/'ipa/xcode'
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMTabletPad=True, DMExternalGameData=True, DMExternalDataVersion=1, DMLocalDataManagement=True,
                DMExternalDataIdentity=manifest['identity'], DMExternalRomFSMarker=MARKER,
                DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(), LSSupportsOpeningDocumentsInPlace=True,
                UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    settings_path = project/'Gen/dm/launcher.json'
    settings = json.loads(settings_path.read_text())
    rows = {r['env']:r for r in settings['settings']}
    defaults = {'DM_RENDER_SCALE':'1.0','DM_OPMODE':'0','DM_SCREEN_ASPECT':'0','DM_PICTURE_FIT':'fit',
                'DM_FPS_TARGET':'30','DM_PRESENT_UPSCALE':'off','DM_PHONE_MOTION':'1','DM_PAD_SWAP_FACE':'0'}
    assert rows['DM_RENDER_SCALE']['base']['handheld']==[1280,720]
    for name,value in defaults.items(): rows[name]['default']=value
    rows['DM_LANG']['options']=[v for v in rows['DM_LANG']['options'] if v[0] in {'zh-Hans','zh-Hant','ja','en-US','en-GB'}]
    settings_path.write_text(json.dumps(settings,separators=(',',':')))
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{DISPLAY} ({TITLE})',
        '-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',derived,
        'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(derived), 'SYMROOT='+str(derived/'Build/Products'),
        'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
    ipa = out/'ZeldaBreathOfTheWild.ipa'
    skip = [item for n in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc')
            for item in ('--skip',APP+n)]
    built = derived/'Build/Products/Release-iphoneos/DmIOS.app'
    run(sys.executable,repo/'dm/ios/tools/pack_ipa.py',ipa,*skip,APP.rstrip('/')+'='+str(built))
    with zipfile.ZipFile(ipa) as z:
        info = plistlib.loads(z.read(APP+'Info.plist'))
        executable = z.read(APP+info['CFBundleExecutable'])
        if (z.testzip() or info['DTSDKName'] != 'iphoneos27.2' or info['CFBundleIdentifier'] != bundle
            or any(n.startswith(APP+key) for n in z.namelist() for key in ('romfs','msl/','aoc/'))
            or any(token not in executable for token in (b'Classic 3D\0', b'iPad 3D\0', b'DmBotwPadLayout\0'))):
            raise ValueError('Invalid external-data IPA')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
