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

SOURCE = 'a0cad7e06a0821c52477ff20dbc53d6126748c54'
CHAIN = '9c1a9324c032'
TITLE = '01007EF00011E000'
MAIN = 'cd57b23fa4bbad65803d9788c01821ee'
APP = 'Payload/DmIOS.app/'
MARKER = 'Pack/Bootup_Graphics.pack'
DISPLAY = 'Zelda Breath of the Wild 1.9.0'


def main(repo, archive, shader_archive, work, out):
    repo, archive, shader_archive, work, out = (Path(p).resolve() for p in (repo, archive, shader_archive, work, out))
    if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE:
        raise ValueError('Unexpected upstream source')
    preflight = os.environ.get('BOTW_COMPILE_PREFLIGHT') == '1'
    work.mkdir()
    out.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(work, filter='data')
    with tarfile.open(shader_archive) as stream:
        path = f'profile/{TITLE}/shader_map.tsv'
        previous_map = stream.extractfile(path).read().decode('utf-8')
        current_map = (repo/'dm/games'/TITLE/'shader_map.tsv').read_text()
        def rows(text):
            return [line for line in text.splitlines() if line and not line.startswith(('#','package\t'))]
        if rows(previous_map) != rows(current_map):
            raise ValueError('The authenticated shader sources use a different upstream map')
        packages = [entry for entry in stream if entry.isfile() and entry.name.startswith('shader/pkg/')]
        if not packages:
            raise ValueError('Missing shader source packages')
        stream.extractall(work, members=packages, filter='data')
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
    if preflight:
        fingerprint = subprocess.check_output([sys.executable,str(repo/'dm/gfx/tools/dmsh_chain.py'),'--inputs'],
                                              env=env,text=True).strip()
        ios = shader/'ios'
        sample = ios/f'b-{CHAIN}'
        sample.mkdir(parents=True)
        (sample/'inputs.tsv').write_text(f'game\t{TITLE}\ninputs\t{fingerprint}\n')
        (sample/'compile-check.metallib').write_bytes(b'compile-check')
        profile = repo/'dm/games'/TITLE
        for n in ('c1_full.tsv','cb_extent.tsv'):
            (profile/n).write_text(f'# chain b-{CHAIN} inputs {fingerprint} game {TITLE}\n')
    else:
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
    rows = {r['env']:r for r in json.loads((project/'Gen/dm/launcher.json').read_text())['settings']}
    for name, wanted in (('DM_FPS_TARGET','30'), ('DM_OPMODE','0'), ('DM_PHONE_MOTION','1'), ('DM_PAD_SWAP_FACE','0')):
        if rows[name]['default'] != wanted:
            raise ValueError(f'Unexpected default for {name}')
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{DISPLAY} ({TITLE})',
        '-configuration','Release','-destination','generic/platform=iOS','-derivedDataPath',derived,
        'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(derived), 'SYMROOT='+str(derived/'Build/Products'),
        'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
    if preflight:
        print('iOS native compile preflight passed')
        return
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
