"""Compile the provisional BannerSaga shaders and an external-data IPA."""
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
TITLE = '0100465008756000'
VERSION = 'v131072'
MAIN = '1a21c8b4419b207fde1e184efaf311e1'
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
    if MAIN not in (patch/'main.fixups.tsv').read_text():
        raise ValueError('Unexpected rewritten BannerSaga main')
    import profile_guess, nacp
    build.pg, build.nacp = profile_guess, nacp
    build.chain_header(Path(sys.executable), repo, env, logs)
    subprocess.run(['git','-C',str(repo),'apply',str(Path(__file__).resolve().parents[2]/'.github/banner-saga-gl-es300.patch')],check=True)
    roots = [extract/'RomFS', extract/'ExeFS/main']
    ios = build.build_gl_shaders(Path(sys.executable), repo, roots, work/'shader', env, logs, g, provisional=True)
    import gl_shaders
    expected = {hashlib.sha256(s).hexdigest()[:16] for s, _, _ in gl_shaders.sources([str(r) for r in roots])}
    libs = ios/'gl'
    table = (libs/'gl_shaders.tsv').read_bytes()
    actual = {line.split('\t')[0] for line in table.decode().splitlines() if line and not line.startswith('#')}
    if not expected or actual != expected:
        raise ValueError('OpenGL shader coverage differs from the complete static source set')
    log = (logs/'gl_shaders.log').read_text(errors='replace')
    if '[RED]' in log:
        raise ValueError('OpenGL shader translation reported failures')
    inputs = hashlib.sha256(table+(libs/'gl_shaders.metallib').read_bytes()).hexdigest()[:12]
    chain = build.chain_of(repo)
    (libs/'inputs.tsv').write_text('chain\t'+chain+'\ngame\t'+TITLE+'\ninputs\t'+inputs+'\n')
    stamp = {'inputs':inputs}
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
            manifest['files'].append(dict(path=f'msl/gl/{path.name}', size=len(payload),
                                          sha256=hashlib.sha256(payload).hexdigest()))
    raw = json.dumps(manifest, separators=(',', ':')).encode()
    (output/'game-data.json').write_bytes(raw)
    apply_runtime.apply(repo, source=SOURCE)
    display = 'Banner Saga'
    env.update(W=str(work/'ipa'), PATCHED=str(patch), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='gl', FONT_PY=sys.executable, DM_DISPLAY_NAME=display,
               DM_BUNDLE_ID='org.nxnative.'+TITLE.lower(), DM_APP_VERSION='2.59.06', DM_LANG='zh-Hans', DM_PSO_GPUS='none',
               DM_ENTITLEMENTS='', DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO',
               DM_XCODE_DERIVED_DATA=str(work/'xcode-dd'))
    def run(*args):
        subprocess.run([str(x) for x in args], env=env, check=True)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode')
    project = work/'ipa/xcode'; plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1, DMLocalDataManagement=True, DMExternalDataIdentity=manifest['identity'],
                DMExternalRomFSMarker='tbs_config.ini', DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),
                LSSupportsOpeningDocumentsInPlace=True, UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    dd = work/'xcode-dd'
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{display} ({TITLE})','-configuration','Release',
        '-destination','generic/platform=iOS','-derivedDataPath',dd,'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
        'CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO','DM_XCODE_OUTPUT_ROOT='+str(dd),
        'SYMROOT='+str(dd/'Build/Products'),'OBJROOT='+str(dd/'Build/Intermediates.noindex'),'build')
    ipa = output/'BannerSaga.ipa'
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for item in ('--skip',APP+name)]
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', ipa, *skip,
        APP.rstrip('/')+'='+str(dd/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(ipa) as z:
        if z.testzip() or ipa.stat().st_size >= 1_000_000_000:
            raise ValueError('Launcher validation failed')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
