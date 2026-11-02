"""Perform the Windows-capable extraction, survey and rewrite before cloud compilation."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('work', type=Path)
    parser.add_argument('--keys', required=True, type=Path)
    parser.add_argument('--resume-shaders', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    work = args.work.resolve()
    title = 0x010016100A186000
    tools = Path('D:/Users/xly/Downloads/roms/switch/01008D7016438000-work/tools')
    dotnet = tools / 'dotnet'
    nx = tools / 'nx_extract/nx_extract.exe'
    if not nx.is_file():
        raise SystemExit('Build nx_extract in the local work directory first')
    env = dict(os.environ, DOTNET_ROOT=str(dotnet), DOTNET_ROOT_X64=str(dotnet),
               PATH=str(dotnet) + os.pathsep + os.environ['PATH'],
               DM_GAME=f'{title:016X}', GAME=f'{title:016X}', PYTHONUTF8='1',
               DM_REWRITE_J='1', J='3', DM_GAMES_FIRST='1', WORK=str(work / 'tmp'), DM_ROOT=str(work))
    os.environ.update(env)
    sys.path.insert(0, str(repo / 'dm/games'))
    sys.path.insert(0, str(repo / 'dm/tools'))
    spec = importlib.util.spec_from_file_location('nsp_build', repo / 'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    import profile_guess
    import nacp
    import game
    build.pg, build.nacp = profile_guess, nacp
    build.PROG.mode = 'lines'
    # Upstream's builder expects a Unix apphost filename. Use the current source's
    # already-built Windows apphost, keeping all derived files outside the repo.
    build.build_nx_extract = lambda *_: nx
    # Python 3.12 has no shutil.rmtree(onexc=...). Preserve upstream's missing-path
    # behavior without changing the source or removing paths outside this work.
    def remove_derived(path):
        path = Path(path).resolve()
        if not path.is_relative_to(work):
            raise ValueError('Refusing cleanup outside game work directory')
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
    build.rmtree = remove_derived
    original_run = build.run
    def run_scanner(cmd, *pos, **kwargs):
        cmd = list(cmd)
        if len(cmd) > 1 and Path(cmd[1]).name == 'shader_split.py':
            cmd[1] = repo / 'scripts/split_windows_shaders.py'
        return original_run(cmd, *pos, **kwargs)
    build.run = run_scanner
    original_fingerprint = build.fingerprint
    build.fingerprint = lambda *inputs: original_fingerprint(*inputs, ('files', [repo / 'scripts/split_windows_shaders.py']))
    if args.resume_shaders:
        profile = work / f'profile/{title:016X}'
        env.update(DM_GAME=str(profile), DM_GAMES_DIR=str(profile.parent))
        os.environ.update(env)
        build.PROG.plan(1)
        build.split_shaders(Path(sys.executable), repo, [work / 'extract/v65536/RomFS'],
                            [work / 'extract/v65536/ExeFS/main'], work / 'shader/pkg',
                            env, work / 'logs', game.load(str(profile)), provisional=False)
        return
    family = {'base': args.image.resolve(), 'updates': [(65536, args.image.resolve())], 'dlc': []}
    facts = build.survey(work, title, family, args.keys.resolve(), repo, Path(sys.executable), env)
    profile = work / f'profile/{title:016X}'
    shutil.copytree(repo / f'dm/games/{title:016X}', profile, dirs_exist_ok=True)
    env['DM_GAMES_DIR'] = str(profile.parent)
    os.environ['DM_GAMES_DIR'] = env['DM_GAMES_DIR']
    game_profile = game.load(str(profile))
    version = 'v65536'
    extracted = work / 'extract' / version
    if not (extracted / 'ExeFS/main').exists():
        extracted.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(nx), str(args.keys.resolve()), str(args.image.resolve()),
                        str(args.image.resolve()), str(extracted), '--app', f'{title:016x}'], env=env, check=True)
    mismatch = build.build_mismatch(extracted, version, game_profile)
    if mismatch:
        raise ValueError('Game build does not match SteamWorld Heist profile: ' + repr(mismatch))
    print('All module build IDs match the registered SteamWorld Heist 2.2.1 profile', flush=True)
    logs = work / 'logs'
    build.rewrite(Path(sys.executable), repo, extracted / 'ExeFS',
                  work / f'patched_{version}', env, logs, game_profile, provisional=False)
    game_profile = build.refine_after_rewrite(game_profile, extracted, work / f'patched_{version}')
    build.split_shaders(Path(sys.executable), repo, [extracted / 'RomFS'],
                        [extracted / 'ExeFS/main'], work / 'shader/pkg',
                        env, logs, game_profile, provisional=False)
    print(f'Local survey, merged extraction, rewrite and shader split complete: {work}', flush=True)


if __name__ == '__main__':
    main()
