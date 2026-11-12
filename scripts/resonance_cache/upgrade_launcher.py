"""Rebuild an external-data launcher using its existing shader identity."""
import os
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import zipfile

from apply_runtime import apply, install_tablet_sources
from build_cache_launcher import run
from build_botw import map_rows, verify_comparison_settings

SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'
APP = 'Payload/DmIOS.app/'
VERSIONS = {'0100CC80140F8000': ('v262144', 'v262144', 'TRIANGLE STRATEGY'),
            '010054B01AD92000': ('v262144', 'merged', 'Unicorn Overlord'),
            '0100A3501946E000': ('v131072', 'v131072', 'OCTOPATH TRAVELER II'),
            '010055D009F78000': ('v327680', 'v327680', 'Fire Emblem Three Houses'),
            '0100F3400332C000': ('v917504', 'v917504', 'Xenoblade Chronicles 2'),
            '01007EF00011E000': ('v786432', 'v786432', 'Zelda Breath of the Wild')}
BOTW_TITLE = '01007EF00011E000'
XENOBLADE_TITLE = '0100F3400332C000'
FACE_SETTING = 'DM_PAD_SWAP_FACE'


def verify_botw190_settings(old, new):
    verify_comparison_settings(new)
    verify_swap_settings(old, new)


def verify_swap_settings(old, new):
    toggle = [r for r in new['settings'] if r['env'] == FACE_SETTING]
    if (len(toggle) != 1 or
        any(toggle[0].get(k) != v for k, v in dict(kind='toggle', section='Controls', default='0', on='1', off='0').items())):
        raise ValueError('Physical controller swap is missing or enabled by default')
    if dict(new, settings=[r for r in new['settings'] if r['env'] != FACE_SETTING]) != old:
        raise ValueError('A previous launcher setting changed')


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
    comparison = title == BOTW_TITLE and old['CFBundleShortVersionString'] == '1.9.0'
    xenoblade = title == XENOBLADE_TITLE
    if xenoblade and (old['CFBundleShortVersionString'] != '2.0.2' or
                      old['CFBundleIdentifier'] != 'org.nxnative.0100f3400332c000' or
                      identity['main_build'] != 'e3938fa78579c1cab27fb0ecef1314e8'):
        raise ValueError('Unexpected Xenoblade Chronicles 2 launcher identity')
    if comparison:
        version = extraction = 'v1114112'
        display = old['CFBundleDisplayName']
        if (identity['main_build'] != 'cd57b23fa4bbad65803d9788c01821ee'
            or old['CFBundleIdentifier'] != 'org.nxnative.01007ef00011e000.v190' or not old.get('DMTabletPad')):
            raise ValueError('Unexpected Breath of the Wild 1.9.0 launcher identity')
    patch = work / f'patched_{version}'
    if f'# BUILD_ID\t{identity["main_build"]}\n' not in (patch / 'main.fixups.tsv').read_text():
        raise ValueError('Rewritten main differs from the installed data build')
    extract = work / 'extract' / extraction
    derived = work / 'profile' / title
    profile = derived if (derived / 'game.tsv').is_file() else repo / 'dm/games' / title
    if comparison:
        registered = repo / 'dm/games' / title
        if profile != derived or map_rows(profile/'shader_map.tsv') != map_rows(registered/'shader_map.tsv'):
            raise ValueError('Profile does not match registered 1.9.0 shader conflicts')
        name = 'shader_map.tsv.conflicts.tsv'
        (profile/name).write_bytes((registered/name).read_bytes())
    for name in ('c1_full.tsv', 'cb_extent.tsv'):
        (profile / name).write_bytes((metadata / name).read_bytes())
    tablet_pad = comparison or xenoblade or (title == BOTW_TITLE and os.environ.get('BOTW_TABLET_PAD') == '1')
    if tablet_pad:
        install_tablet_sources(repo)
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
    if comparison or xenoblade:
        validate = verify_botw190_settings if comparison else verify_swap_settings
        validate(json.loads((metadata/'launcher.json').read_bytes()),
                 json.loads((project/'Gen/dm/launcher.json').read_bytes()))
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    for key in ('DMExternalGameData', 'DMExternalDataVersion', 'DMExternalDataIdentity',
                'DMExternalRomFSMarker', 'DMShaderCacheManifest'):
        info[key] = old[key]
    info['DMLocalDataManagement'] = True
    if tablet_pad:
        info['DMTabletPad'] = True
    if comparison or xenoblade:
        for key in ('LSSupportsOpeningDocumentsInPlace', 'UIFileSharingEnabled'):
            info[key] = old[key]
    plist.write_bytes(plistlib.dumps(info))
    run('xcodebuild', '-project', project/'DmIOS.xcodeproj', '-scheme', f'{display} ({title})',
        '-configuration', 'Release', '-destination', 'generic/platform=iOS', '-derivedDataPath', dd,
        'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=',
        'DM_COPY_GAME_RESOURCES=NO', 'DM_XCODE_OUTPUT_ROOT='+str(dd), 'SYMROOT='+str(dd/'Build/Products'),
        'OBJROOT='+str(dd/'Build/Intermediates.noindex'), 'build', env=env)
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc')
            for item in ('--skip', APP+name)]
    built_app = dd/'Build/Products/Release-iphoneos/DmIOS.app'
    if comparison or xenoblade:
        for name in ('shader_pairs.tsv', 'pso_pairs.tsv'):
            table = built_app/'dm'/name
            payload = table.read_bytes().replace(b'\r\n', b'\n')
            if b'\r' in payload or not payload.endswith(b'\n'):
                raise ValueError('Invalid shader pair table: '+name)
            table.write_bytes(payload)
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', output, *skip, APP.rstrip('/')+'='+str(built_app), env=env)
    with zipfile.ZipFile(output) as package:
        if package.testzip() or any(n.startswith((APP+'romfs/', APP+'msl/', APP+'aoc/')) for n in package.namelist()):
            raise ValueError('Unexpected launcher contents')


if __name__ == '__main__':
    main(*sys.argv[1:])
