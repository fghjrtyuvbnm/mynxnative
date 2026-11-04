"""Relink a previously bundled IPA for external data without retranslating shaders."""
import importlib
import importlib.util
import os
from pathlib import Path
import plistlib
import sys
import tarfile

from apply_runtime import apply
from build_cache_launcher import run

SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'
GAMES = {
    'taiko': ('v262144', 'Taiko Risshiden V DX'),
    'refrain': ('v131072', 'Labyrinth of Refrain'),
    'sentinels': ('v0', '13 Sentinels: Aegis Rim'),
}
APP = 'Payload/DmIOS.app/'


def main(game_name, repo, archive, overlay, work, output):
    repo, work, output = map(lambda p: Path(p).resolve(), (repo, work, output))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    original = importlib.import_module('cloud_compile_' + game_name)
    manifest = original.restore(archive, work)
    title = original.TITLE
    metadata = work / 'upgrade'
    with tarfile.open(overlay) as tar:
        tar.extractall(metadata, filter='data')
    old = plistlib.loads((metadata/'Info.plist').read_bytes())
    external = plistlib.loads((metadata/'external.plist').read_bytes())
    identity = external['DMExternalDataIdentity']
    assert title == identity['title_id']
    version, display = GAMES[game_name]
    patch = work/f'patched_{version}'
    extract = work/'extract'/version
    assert f'# BUILD_ID\t{identity["main_build"]}\n' in (patch/'main.fixups.tsv').read_text()
    if game_name == 'taiko':
        assert manifest.get('frame_rate_patch') is True and '0x4444dc' in (patch/'main.cuts.tsv').read_text()
    dd = work/'xcode-dd'
    env = dict(os.environ, GAME=title, DM_GAME=title, DM_GAMES_DIR=str(work/'profile'), DM_GAMES_FIRST='1',
               DM_ROOT=str(work), WORK=str(work/'tmp'), W=str(work/'ipa'), PATCHED=str(patch),
               ROMFS=str(extract/'RomFS'), MSL_IOS=str(metadata/'msl'), GFXAPI='nvn', FONT_PY=sys.executable,
               DM_DISPLAY_NAME=display, DM_BUNDLE_ID=old['CFBundleIdentifier'], DM_LANG=old['DMLanguage'],
               DM_APP_VERSION=old['CFBundleShortVersionString'], DM_PSO_GPUS='none', DM_ENTITLEMENTS='',
               DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO', DM_XCODE_DERIVED_DATA=str(dd))
    Path(env['WORK']).mkdir()
    os.environ.update(env)
    sys.path[:0] = [str(repo/'dm/games'), str(repo/'dm/tools')]
    import game
    import profile_guess
    spec = importlib.util.spec_from_file_location('upstream_builder', repo/'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    build.pg = profile_guess
    profile = game.load(title)
    if old.get('DMTouchOnly'):
        import touch_build
        profile = touch_build.configure_profile(build, profile)
        touch_build.patch_ios_source(repo)
    if int(profile.get('sys_resource', '0'), 0) == 0:
        profile = build.refine_after_rewrite(profile, extract, patch)
    assert profile.get('romfs_marker') == external['DMExternalRomFSMarker']
    for name in ('c1_full.tsv', 'cb_extent.tsv'):
        (profile.dir/name).write_bytes((metadata/name).read_bytes())
    apply(repo, source=SOURCE)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode', env=env)
    project = work/'ipa/xcode'
    plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(external)
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


if __name__ == '__main__':
    main(*sys.argv[1:])
