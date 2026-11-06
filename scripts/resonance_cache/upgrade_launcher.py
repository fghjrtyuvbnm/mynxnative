"""Rebuild an external-data launcher using its existing shader identity."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import zipfile

from apply_runtime import apply
from build_cache_launcher import run

SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'
APP = 'Payload/DmIOS.app/'
VERSIONS = {'010054B01AD92000': ('v262144', 'merged', 'Unicorn Overlord'),
            '0100A3501946E000': ('v131072', 'v131072', 'OCTOPATH TRAVELER II'),
            '010055D009F78000': ('v327680', 'v327680', 'Fire Emblem Three Houses'),
            '01007EF00011E000': ('v786432', 'v786432', 'Zelda Breath of the Wild')}


def main(repo, archive, overlay, work, output):
    repo, work, output = map(lambda p: Path(p).resolve(), (repo, work, output))
    work.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter='data')
    metadata = work / 'upgrade'
    with tarfile.open(overlay) as tar:
        tar.extractall(metadata, filter='data')
    old = plistlib.loads((metadata / 'Info.plist').read_bytes())
    identity = old['DMExternalDataIdentity']
    title, chain = identity['title_id'], identity['shader_chain']
    version, extraction, display = VERSIONS[title]
    patch = work / f'patched_{version}'
    if f'# BUILD_ID\t{identity["main_build"]}\n' not in (patch / 'main.fixups.tsv').read_text():
        raise ValueError('Rewritten main differs from the installed data build')
    extract = work / 'extract' / extraction
    derived = work / 'profile' / title
    profile = derived if (derived / 'game.tsv').is_file() else repo / 'dm/games' / title
    for name in ('c1_full.tsv', 'cb_extent.tsv'):
        (profile / name).write_bytes((metadata / name).read_bytes())
    apply(repo, source=SOURCE)
    dd = work / 'xcode-dd'
    env = dict(os.environ, GAME=title, DM_GAME=title, DM_ROOT=str(work), WORK=str(work/'tmp'),
               W=str(work/'ipa'), PATCHED=str(patch), ROMFS=str(extract/'RomFS'),
               MSL_IOS=str(metadata/'msl'), GFXAPI='nvn', FONT_PY=sys.executable,
               DM_DISPLAY_NAME=display, DM_BUNDLE_ID=old['CFBundleIdentifier'],
               DM_APP_VERSION=old['CFBundleShortVersionString'], DM_LANG=old['DMLanguage'],
               DM_PSO_GPUS='none', DM_ENTITLEMENTS='', DM_ICON=str(extract/'icon.jpg'), AOC='',
               DM_COPY_ROMFS='NO', DM_XCODE_DERIVED_DATA=str(dd))
    if profile == derived:
        env.update(DM_GAMES_DIR=str(derived.parent), DM_GAMES_FIRST='1')
    if f'"{chain}"' not in (repo/'dm/gfx/nvn/dmsh_chain.h').read_text():
        raise ValueError('Shader chain differs from the installed data')
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode', env=env)
    project = work/'ipa/xcode'
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    for key in ('DMExternalGameData', 'DMExternalDataVersion', 'DMExternalDataIdentity',
                'DMExternalRomFSMarker', 'DMShaderCacheManifest'):
        info[key] = old[key]
    info['DMLocalDataManagement'] = True
    plist.write_bytes(plistlib.dumps(info))
    run('xcodebuild', '-project', project/'DmIOS.xcodeproj', '-scheme', f'{display} ({title})',
        '-configuration', 'Release', '-destination', 'generic/platform=iOS', '-derivedDataPath', dd,
        'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=',
        'DM_COPY_GAME_RESOURCES=NO', 'DM_XCODE_OUTPUT_ROOT='+str(dd), 'SYMROOT='+str(dd/'Build/Products'),
        'OBJROOT='+str(dd/'Build/Intermediates.noindex'), 'build', env=env)
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc')
            for item in ('--skip', APP+name)]
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', output, *skip,
        APP.rstrip('/')+'='+str(dd/'Build/Products/Release-iphoneos/DmIOS.app'), env=env)
    with zipfile.ZipFile(output) as package:
        if package.testzip() or any(n.startswith((APP+'romfs/', APP+'msl/', APP+'aoc/')) for n in package.namelist()):
            raise ValueError('Unexpected launcher contents')


if __name__ == '__main__':
    main(*sys.argv[1:])
