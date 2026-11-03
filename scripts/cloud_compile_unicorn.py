"""Compile locally prepared modules/shaders on Apple; leave full RomFS on Windows."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import shutil
import zipfile

TITLE = '010054B01AD92000'
SOURCE = 'cde88f62068e3d879b083b1a86a7fd78610c7b7b'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def restore(archive, work):
    work.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r:*') as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name:
                raise ValueError('Unsafe archive path')
            if not (member.isfile() or member.isdir()):
                raise ValueError('Archive links are forbidden')
        package.extractall(work, filter='data')
    manifest = json.loads((work / 'input-manifest.json').read_text())
    if manifest['title_id'] != TITLE or manifest['source'] != SOURCE:
        raise ValueError('Wrong input identity')
    for row in manifest['files']:
        path = (work / row['path']).resolve()
        if not path.is_relative_to(work.resolve()) or sha(path) != row['sha256']:
            raise ValueError('Input integrity mismatch')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('work', type=Path)
    parser.add_argument('repo', type=Path)
    args = parser.parse_args()
    work, repo = args.work.resolve(), args.repo.resolve()
    manifest = restore(args.archive, work)
    env = dict(os.environ, DM_GAME=TITLE, GAME=TITLE, DM_GAMES_DIR=str(work / 'profile'),
               DM_GAMES_FIRST='1', DM_ROOT=str(work), WORK=str(work / 'tmp'), J='3', PYTHONUTF8='1')
    Path(env['WORK']).mkdir(parents=True, exist_ok=True)
    os.environ.update(env)
    sys.path[:0] = [str(repo / 'dm/games'), str(repo / 'dm/tools')]
    import game
    import profile_guess
    spec = importlib.util.spec_from_file_location('nsp_build', repo / 'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    build.pg = profile_guess
    profile = game.load(TITLE)
    logs = work / 'logs'
    logs.mkdir(exist_ok=True)
    build.PROG.mode = 'lines'
    build.PROG.plan(4)
    build.configure_dotnet(env)
    translator = repo / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
    build.check_prereqs(env, translator)
    build.chain_header(Path(sys.executable), repo, env, logs)
    shader = work / 'shader'
    ios = build.build_shaders(Path(sys.executable), repo, shader, translator,
                              env, logs, profile, build.package_key(shader / 'pkg'))
    result = json.loads((shader / 'cache' / ('b-' + build.chain_of(repo)) / '_b_build.json').read_text())
    if len(result) != manifest['shader_count'] or any(row['st'] != 'ok' for row in result):
        raise ValueError('Not every locally discovered shader compiled successfully')
    output = work / 'output'
    output.mkdir()
    template = output / 'UnicornOverlordAsia-template.ipa'
    compile_env = dict(env, W=str(work / 'ipa'), PATCHED=str(work / 'patched_v262144'),
                       ROMFS=str(work / 'extract/merged/RomFS'), MSL_IOS=str(ios),
                       AOC=str(work / 'aoc'), FONT_PY=sys.executable, DM_COPY_ROMFS='NO',
                       DM_ENTITLEMENTS='', DM_PSO_GPUS='none', DM_LANG='zh-Hant',
                       DM_DISPLAY_NAME='Unicorn Overlord', DM_APP_VERSION='1.05',
                       DM_BUNDLE_ID='org.nxnative.' + TITLE.lower())
    build.run(['bash', repo / 'dm/ios/tools/build_ipa.sh', template],
              logs / 'compile-template.log', env=compile_env)
    partial = template.with_suffix('.partial')
    with zipfile.ZipFile(template) as original, zipfile.ZipFile(partial, 'w') as final:
        for entry in original.infolist():
            with original.open(entry) as source, final.open(entry, 'w') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
        final.write(work / 'romfs.id', 'Payload/DmIOS.app/romfs.id')
    partial.replace(template)
    print(f'Unsigned template compiled: {template}; full game resources must be added on Windows', flush=True)


if __name__ == '__main__':
    main()
