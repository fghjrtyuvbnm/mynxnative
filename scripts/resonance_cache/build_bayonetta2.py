"""Compile the version-derived Bayonetta 2 shaders and an external-data IPA."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'
TITLE = '01007960049A0000'
VERSION = 'v65536'
EXPECTED_VERSION = '1.1'
APP = 'Payload/DmIOS.app/'


def map_rows(path):
    return [line.split('\t', 4) for line in path.read_text(encoding='utf-8').splitlines()
            if line and not line.startswith(('#', 'package\t'))]


def main(repo, archive, work, output):
    repo, work, output = map(lambda p: Path(p).resolve(), (repo, work, output))
    work.mkdir(parents=True)
    output.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter='data')
    os.environ.update(DM_GAME=TITLE, GAME=TITLE, DM_GAMES_DIR=str(work/'profile'), DM_GAMES_FIRST='1')
    sys.path[:0] = [str(repo/'dm/games'), str(repo/'dm/gfx/tools'), str(repo/'dm/tools')]
    import game
    import apply_runtime
    profile = work/'profile'/TITLE
    g = game.load(TITLE)
    spec = importlib.util.spec_from_file_location('upstream_builder', repo/'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    env = dict(os.environ, GAME=TITLE, DM_GAME=TITLE, DM_ROOT=str(work), WORK=str(work/'tmp'), J='3')
    (work/'tmp').mkdir()
    logs = work/'logs'; logs.mkdir()
    build.PROG.mode = 'lines'; build.PROG.plan(5)
    build.configure_dotnet(env)
    patch = work/f'patched_{VERSION}'
    extract = work/'extract'/VERSION
    facts = json.loads((work/'preparation.json').read_text())
    main_build = facts['main']
    if facts['title'] != TITLE or facts['display'] != EXPECTED_VERSION:
        raise ValueError('Unexpected prepared release')
    if main_build not in (patch/'main.fixups.tsv').read_text():
        raise ValueError('Unexpected rewritten Bayonetta2 main')
    import profile_guess, nacp
    build.pg, build.nacp = profile_guess, nacp
    build.chain_header(Path(sys.executable), repo, env, logs)
    # This release has no virtual-address resource; its derived memory layout
    # was refined against the actual rewritten modules on the local machine.
    if g.int('sys_resource') != 0:
        raise ValueError('Unexpected virtual-address-memory requirement')
    if not map_rows(profile/'shader_map.tsv'):
        raise ValueError('No prepared shaders')
    translator = repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
    ios = build.build_shaders(Path(sys.executable), repo, work/'shader', translator, env, logs, g)
    chain = build.chain_of(repo)
    libs = ios/f'b-{chain}'
    stamp = dict(line.split('\t',1) for line in (libs/'inputs.tsv').read_text().splitlines() if line and not line.startswith('#'))
    for _, _, stage, key, _ in map_rows(profile/'shader_map.tsv'):
        meta = json.loads((libs/f'{key}_b.json').read_text())
        if not (libs/f'{key}_b.metallib').is_file() and not (stage == 'geometry' and 'gs_slice' in meta):
            raise ValueError('Missing translated shader '+key)
    manifest = {'format_version': 1,
                'identity': dict(title_id=TITLE, main_build=main_build, shader_chain=chain, shader_inputs=stamp['inputs']),
                'files': json.loads((work/'game-assets.json').read_text())}
    with (output/'shaders.pack').open('xb') as stream:
        stream.write(b'FFRSMSL1')
        for path in sorted(libs.iterdir()):
            if path.suffix not in ('.json', '.metallib', '.tsv'):
                continue
            payload = path.read_bytes()
            stream.write(payload)
            manifest['files'].append(dict(path=f'msl/b-{chain}/{path.name}', size=len(payload),
                                          sha256=hashlib.sha256(payload).hexdigest()))
    raw = json.dumps(manifest, separators=(',', ':')).encode()
    (output/'game-data.json').write_bytes(raw)
    apply_runtime.apply(repo, source=SOURCE)
    display = 'Bayonetta 2'
    env.update(W=str(work/'ipa'), PATCHED=str(patch), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_DISPLAY_NAME=display,
               DM_BUNDLE_ID='org.nxnative.'+TITLE.lower(), DM_APP_VERSION='1.1', DM_LANG='zh-Hans', DM_PSO_GPUS='none',
               DM_ENTITLEMENTS='', DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO',
               DM_XCODE_DERIVED_DATA=str(work/'xcode-dd'))
    def run(*args):
        subprocess.run([str(x) for x in args], env=env, check=True)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode')
    project = work/'ipa/xcode'; plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1, DMLocalDataManagement=True, DMExternalDataIdentity=manifest['identity'],
                DMExternalRomFSMarker='data002.cpk', DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),
                LSSupportsOpeningDocumentsInPlace=True, UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    dd = work/'xcode-dd'
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{display} ({TITLE})','-configuration','Release',
        '-destination','generic/platform=iOS','-derivedDataPath',dd,'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
        'CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO','DM_XCODE_OUTPUT_ROOT='+str(dd),
        'SYMROOT='+str(dd/'Build/Products'),'OBJROOT='+str(dd/'Build/Intermediates.noindex'),'build')
    ipa = output/'Bayonetta2.ipa'
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for item in ('--skip',APP+name)]
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', ipa, *skip,
        APP.rstrip('/')+'='+str(dd/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(ipa) as z:
        if z.testzip() or ipa.stat().st_size >= 1_000_000_000:
            raise ValueError('Launcher validation failed')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
