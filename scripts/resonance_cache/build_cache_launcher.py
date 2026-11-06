"""Rebuild only the FFR launcher, retaining the exact external shader chain."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import zipfile

SOURCE = 'cdc6cef6b0250fcb54a061e4c55d56382b5d18ad'
TITLE = '0100B8A026F14000'
BUILD = 'b7f965b9d7227db8e29f04e84ea7331b'
CHAIN = 'd374e783beec'
INPUTS = '087b5d58cc3d'
APP = 'Payload/DmIOS.app/'


def set_defaults(profile):
    path = profile / 'game.tsv'
    lines = path.read_text(encoding='utf-8').splitlines()
    updates = {'fps_target': '30', 'op_mode': 'handheld'}
    lines = [line for line in lines if line.split('\t', 1)[0] not in updates]
    lines.extend(key + '\t' + value for key, value in updates.items())
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def check_defaults(settings):
    rows = {r['env']: r['default'] for r in settings['settings']}
    if rows.get('DM_FPS_TARGET') != '30' or rows.get('DM_OPMODE') != '0':
        raise ValueError('Expected 30 fps and 1280x720 handheld defaults')


def run(*args, env=None):
    subprocess.run([str(x) for x in args], env=env, check=True)


def main(repo, work, archive, output):
    from apply_profile import apply as profile_patch
    from apply_runtime import apply as runtime_patch
    repo, work, output = map(lambda x: Path(x).resolve(), (repo, work, output))
    work.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter='data')
    from restore_reference import restore
    restore(work)
    shader = work / 'msl'
    marker = 'FFRS/Content/Paks/FFRS-Switch.ucas'
    romfs = work / 'extract/v1/RomFS'
    meta = json.loads((work / 'cache-build.json').read_text())
    digest = meta['manifest_sha256']
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid external manifest digest')
    profile_patch(repo)
    runtime_patch(repo)
    profile = repo / 'dm/games' / TITLE
    for name in ('c1_full.tsv', 'cb_extent.tsv'):
        (profile/name).write_bytes((work/name).read_bytes())
    set_defaults(profile)
    env = dict(os.environ, GAME=TITLE, DM_GAME=TITLE, DM_ROOT=str(work), WORK=str(work/'tmp'),
               W=str(work/'ipa'), PATCHED=str(work/'patched_v1'), ROMFS=str(romfs), MSL_IOS=str(shader),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_LANG='zh-Hans', DM_DISPLAY_NAME='FINAL FANTASY RESONANCE',
               DM_BUNDLE_ID='org.nxnative.'+TITLE.lower(), DM_APP_VERSION='1.0.1', DM_PSO_GPUS='none', DM_ENTITLEMENTS='',
               DM_ICON=str(work/'extract/v1/icon.jpg'), AOC='', DM_SHOW_FPS='1', DM_XCODE_DERIVED_DATA=str(work/'xcode-dd'))
    if BUILD not in (work/'patched_v1/main.fixups.tsv').read_text():
        raise ValueError('Wrong rewritten main build')
    run(sys.executable, repo/'dm/gfx/tools/dmsh_chain.py', '--header', env=env)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode', env=env)
    project = work/'ipa/xcode'
    settings = project/'Gen/dm/launcher.json'
    check_defaults(json.loads(settings.read_text()))
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1,
                DMLocalDataManagement=True,
                DMExternalDataIdentity=dict(title_id=TITLE, main_build=BUILD, shader_chain=CHAIN, shader_inputs=INPUTS),
                DMExternalRomFSMarker=marker, DMShaderCacheManifest=digest, LSSupportsOpeningDocumentsInPlace=True,
                UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    dd = work/'xcode-dd'
    run('xcodebuild', '-project', project/'DmIOS.xcodeproj', '-scheme', f'FINAL FANTASY RESONANCE ({TITLE})',
        '-configuration', 'Release', '-destination', 'generic/platform=iOS', '-derivedDataPath', dd,
        'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=', 'DM_COPY_GAME_RESOURCES=NO',
        'DM_XCODE_OUTPUT_ROOT='+str(dd), 'SYMROOT='+str(dd/'Build/Products'), 'OBJROOT='+str(dd/'Build/Intermediates.noindex'),
        'build', env=env)
    app = dd/'Build/Products/Release-iphoneos/DmIOS.app'
    args = [sys.executable, repo/'dm/ios/tools/pack_ipa.py', output]
    for name in ('_CodeSignature', 'embedded.mobileprovision', 'romfs', 'msl', 'aoc'):
        args += ['--skip', APP+name]
    run(*args, APP.rstrip('/')+'='+str(app), env=env)
    verify(output, digest)


def verify(output, digest):
    if output.stat().st_size >= 1_000_000_000:
        raise ValueError('IPA exceeded 1 GB')
    with zipfile.ZipFile(output) as z:
        if z.testzip() or any(n.startswith((APP+'romfs/',APP+'msl/',APP+'aoc/')) for n in z.namelist()):
            raise ValueError('IPA integrity or resource separation failed')
        info = plistlib.loads(z.read(APP+'Info.plist'))
        if info.get('DMShaderCacheManifest') != digest or info.get('DMExternalGameData') is not True:
            raise ValueError('Shader cache configuration missing')
        check_defaults(json.loads(z.read(APP+'dm/launcher.json')))
        with z.open(APP+info['CFBundleExecutable']) as f:
            if f.read(8) != bytes.fromhex('cffaedfe0c000001'):
                raise ValueError('Expected arm64 Mach-O')


if __name__ == '__main__':
    main(*sys.argv[1:])

