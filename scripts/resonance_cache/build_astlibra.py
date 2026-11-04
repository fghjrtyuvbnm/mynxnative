"""Capture ASTLIBRA startup shaders and build a provisional external-data IPA."""
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
TITLE = '0100F8D01A06E000'
VERSION = 'v327680'
MAIN = '49588fd435d01bddfa35996dab8b2f1c'
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
    env = dict(os.environ, GAME=TITLE, DM_GAME=TITLE, DM_ROOT=str(work), WORK=str(work/'tmp'), J='3', DM_LANG='zh-Hans')
    (work/'tmp').mkdir()
    logs = work/'logs'; logs.mkdir()
    build.PROG.mode = 'lines'; build.PROG.plan(5)
    build.configure_dotnet(env)
    patch = work/f'patched_{VERSION}'
    extract = work/'extract'/VERSION
    if MAIN not in (patch/'main.fixups.tsv').read_text():
        raise ValueError('Unexpected rewritten ASTLIBRA Revision main')
    build.chain_header(Path(sys.executable), repo, env, logs)
    # Capture-only workaround for the hosted Mac's paravirtual GPU: it lacks
    # Metal 4, so regular NVN initialization aborts before DXLib invokes GLSLC.
    # The existing classic device path supplies buffers while CPU GLSLC runs.
    # Restore the host source before preparing the actual iOS application.
    host_main = repo/'dm/host/main.c'
    original_host_main = host_main.read_text()
    needle = 'int main(int argc, char **argv) {'
    if original_host_main.count(needle) != 1:
        raise ValueError('Pinned Mac host entry changed')
    host_main.write_text(original_host_main.replace(needle, needle +
        '\n    if (getenv("DM_GLSLC_CAPTURE")) { void *mtl_device_classic(void); mtl_device_classic(); }',1))
    try:
        build.capture_glslc(repo, {VERSION:extract}, VERSION, patch, work, env, logs, g)
    finally:
        host_main.write_text(original_host_main)
    build.split_shaders(Path(sys.executable), repo, [extract/'RomFS'], [extract/'ExeFS/main'],
                        work/'shader/pkg', env, logs, g, provisional=True)
    if not map_rows(profile/'shader_map.tsv'):
        raise ValueError('No runtime shaders captured')
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
                'identity': dict(title_id=TITLE, main_build=MAIN, shader_chain=chain, shader_inputs=stamp['inputs']),
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
    display = 'ASTLIBRA Revision'
    env.update(W=str(work/'ipa'), PATCHED=str(patch), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_DISPLAY_NAME=display,
               DM_BUNDLE_ID='org.nxnative.'+TITLE.lower(), DM_APP_VERSION='1.0.7', DM_LANG='zh-Hans', DM_PSO_GPUS='none',
               DM_ENTITLEMENTS='', DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO',
               DM_XCODE_DERIVED_DATA=str(work/'xcode-dd'))
    def run(*args):
        subprocess.run([str(x) for x in args], env=env, check=True)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode')
    project = work/'ipa/xcode'; plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1, DMLocalDataManagement=True, DMExternalDataIdentity=manifest['identity'],
                DMExternalRomFSMarker='DAT/ARTICULAR_000.DAT', DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),
                LSSupportsOpeningDocumentsInPlace=True, UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    dd = work/'xcode-dd'
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{display} ({TITLE})','-configuration','Release',
        '-destination','generic/platform=iOS','-derivedDataPath',dd,'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
        'CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO','DM_XCODE_OUTPUT_ROOT='+str(dd),
        'SYMROOT='+str(dd/'Build/Products'),'OBJROOT='+str(dd/'Build/Intermediates.noindex'),'build')
    ipa = output/'AstlibraRevision.ipa'
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for item in ('--skip',APP+name)]
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', ipa, *skip,
        APP.rstrip('/')+'='+str(dd/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(ipa) as z:
        if z.testzip() or ipa.stat().st_size >= 1_000_000_000:
            raise ValueError('Launcher validation failed')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
