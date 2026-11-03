"""Capture the registered Three Houses runtime shaders and compile an external-data IPA."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile

SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'
TITLE = '010055D009F78000'
VERSION = 'v327680'
MAIN = '89048449ba238c8cf565518b83bf02d3'
APP = 'Payload/DmIOS.app/'


def map_rows(path):
    return [line.split('\t', 4) for line in path.read_text(encoding='utf-8').splitlines()
            if line and not line.startswith(('#', 'package\t'))]


def assemble(work, profile, capture, scanner):
    static = work/'local-shaders'
    indexed = {}
    for name, index, stage, key, _ in map_rows(static/'shader_map.tsv'):
        if name not in indexed:
            indexed[name] = (static/'pkg'/name).read_bytes().split(b'BTCDBTCD')[1:]
    records = {}
    for name, index, stage, key, _ in map_rows(static/'shader_map.tsv'):
        record = b'BTCDBTCD' + indexed[name][int(index)]
        ctl_size, code_size = struct.unpack_from('<2I', record, 0x28)
        ctl = record[0x38+code_size:]
        if len(ctl) != ctl_size or scanner.skey(ctl, record[0x38:0x38+code_size]) != key:
            raise ValueError('Static shader key differs: '+key)
        records[key] = (stage, record)
    for path in sorted(capture.glob('*.glslc')):
        for _, stage, ctl, code in scanner.glslc_shaders(path.read_bytes(), '/glslc_capture/'+path.name):
            key = scanner.skey(ctl, code)
            record = bytearray(b'BTCDBTCD' + bytes(0x30))
            struct.pack_into('<2I', record, 0x28, len(ctl), len(code))
            if key in records:
                raise ValueError('Captured shader duplicates a static key: '+key)
            records[key] = (scanner.STAGE_NAME[stage], bytes(record)+code+ctl)
    expected = map_rows(profile/'shader_map.tsv')
    if set(records) != {r[3] for r in expected}:
        raise ValueError('Shader keys differ from the complete registered map')
    output = work/'shader/pkg'; output.mkdir(parents=True)
    groups = {}
    for name, index, stage, key, _ in expected:
        rows = groups.setdefault(name, {})
        if records[key][0] != stage or int(index) in rows:
            raise ValueError('Registered shader stage/index differs: '+key)
        rows[int(index)] = records[key][1]
    for name, rows in groups.items():
        (output/name).write_bytes(b''.join(rows[i] for i in range(len(rows))))
    print(f'Assembled all {len(records)} registered shaders', flush=True)


def main(repo, archive, work, output, captured_archive=None):
    repo, work, output = map(lambda p: Path(p).resolve(), (repo, work, output))
    work.mkdir(parents=True)
    output.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter='data')
    os.environ.update(DM_GAME=TITLE, GAME=TITLE)
    sys.path[:0] = [str(repo/'dm/games'), str(repo/'dm/gfx/tools'), str(repo/'dm/tools')]
    import game
    import shader_split
    import apply_runtime
    profile = repo/'dm/games'/TITLE
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
        raise ValueError('Unexpected rewritten Three Houses main')
    build.chain_header(Path(sys.executable), repo, env, logs)
    capture = extract/'glslc_capture'
    wanted = build.glslc_wanted(g)
    if captured_archive and Path(captured_archive).is_file():
        capture.mkdir(parents=True)
        with tarfile.open(captured_archive) as tar:
            members = tar.getmembers()
            if (len(members) != len(wanted) or {m.name for m in members} != wanted
                    or any(not m.isfile() or not 0 < m.size <= 16 * 1024 * 1024 for m in members)):
                raise ValueError('Unexpected GLSLC capture archive contents')
            tar.extractall(capture, filter='data')
    capture_only = not capture.is_dir()
    if capture_only:
        shader_map = profile/'shader_map.tsv'
        lines = shader_map.read_text(encoding='utf-8').splitlines()
        shader_map.write_text('\n'.join(line for line in lines if '/glslc_capture/' not in line or line.startswith('#'))+'\n', encoding='utf-8')
        for name in ('shader_facts.tsv', 'shader_pairs.tsv'):
            path = profile/name
            remaining = {r[3] for r in map_rows(shader_map)}
            text = path.read_text(encoding='utf-8').splitlines()
            path.write_text('\n'.join(line for line in text if all(key in remaining for key in re.findall(r'\b[0-9a-f]{16}\b',line)) or line.startswith('#'))+'\n',encoding='utf-8')
        capture_env = work/'capture.env'
        capture_env.write_text('DM_GLSLC_CAPTURE=glslc_capture\n', encoding='utf-8')
        env['DM_ENV_FILE'] = str(capture_env)
        print('Device capture build. The registered runtime shaders must be supplied for a final build.', flush=True)
    elif build.glslc_done(capture) != wanted:
        raise ValueError('Capture files do not match the registered GLSLC outputs')
    assemble(work, profile, capture, shader_split)
    shutil.copyfile(work/'local-shaders/pso_pairs.tsv', work/'shader/pso_pairs.tsv')
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
    display = 'Fire Emblem Three Houses Capture' if capture_only else 'Fire Emblem Three Houses'
    env.update(W=str(work/'ipa'), PATCHED=str(patch), ROMFS=str(extract/'RomFS'), MSL_IOS=str(ios),
               GFXAPI='nvn', FONT_PY=sys.executable, DM_DISPLAY_NAME=display,
               DM_BUNDLE_ID='org.nxnative.'+TITLE.lower(), DM_APP_VERSION='1.2.0', DM_PSO_GPUS='none',
               DM_ENTITLEMENTS='', DM_ICON=str(extract/'icon.jpg'), AOC='', DM_COPY_ROMFS='NO',
               DM_XCODE_DERIVED_DATA=str(work/'xcode-dd'))
    def run(*args):
        subprocess.run([str(x) for x in args], env=env, check=True)
    run('bash', repo/'dm/ios/tools/build_ipa.sh', '--prepare-xcode')
    project = work/'ipa/xcode'; plist = project/'Gen/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(DMExternalGameData=True, DMExternalDataVersion=1, DMExternalDataIdentity=manifest['identity'],
                DMExternalRomFSMarker='DATA1.bin', DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),
                LSSupportsOpeningDocumentsInPlace=True, UIFileSharingEnabled=True)
    plist.write_bytes(plistlib.dumps(info))
    dd = work/'xcode-dd'
    run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',f'{display} ({TITLE})','-configuration','Release',
        '-destination','generic/platform=iOS','-derivedDataPath',dd,'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
        'CODE_SIGN_IDENTITY=','DM_COPY_GAME_RESOURCES=NO','DM_XCODE_OUTPUT_ROOT='+str(dd),
        'SYMROOT='+str(dd/'Build/Products'),'OBJROOT='+str(dd/'Build/Intermediates.noindex'),'build')
    ipa = output/'FireEmblemThreeHouses.ipa'
    skip = [item for name in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for item in ('--skip',APP+name)]
    run(sys.executable, repo/'dm/ios/tools/pack_ipa.py', ipa, *skip,
        APP.rstrip('/')+'='+str(dd/'Build/Products/Release-iphoneos/DmIOS.app'))
    with zipfile.ZipFile(ipa) as z:
        if z.testzip() or ipa.stat().st_size >= 1_000_000_000:
            raise ValueError('Launcher validation failed')
    build.PROG.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
