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
    args = parser.parse_args()
    repo = args.work.resolve() / 'tools/source-build'
    work = args.work.resolve()
    title = 0x0100346017304000
    tools = Path('D:/Users/xly/Downloads/roms/switch/0100F0E0136BE000-work/tools')
    dotnet = tools / 'dotnet'
    nx = tools / 'nx_extract/nx_extract.exe'
    if not nx.is_file():
        raise SystemExit('Build nx_extract in the local work directory first')
    env = dict(os.environ, DOTNET_ROOT=str(dotnet), DOTNET_ROOT_X64=str(dotnet),
               PATH=str(dotnet) + os.pathsep + os.environ['PATH'],
               DM_GAME=f'{title:016X}', GAME=f'{title:016X}', PYTHONUTF8='1',
               DM_REWRITE_J='1', DM_GAMES_FIRST='1', WORK=str(work / 'tmp'), DM_ROOT=str(work))
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
    family = {'base': args.image.resolve(), 'updates': [(262144, args.image.resolve())], 'dlc': [(0x0100346017305001, 0, args.image.resolve())]}
    facts = build.survey(work, title, family, args.keys.resolve(), repo, Path(sys.executable), env)
    facts['survey'] = str(work / f'{title:016X}_survey/survey.md')
    profile = work / f'profile/{title:016X}'
    build.write_profile(profile, title, facts)
    # Like Taiko Risshiden V DX, this binary imports GetTouchScreenState and
    # GetGestureStates. Start in handheld touch mode; no foreign address patches.
    settings = profile / 'game.tsv'
    text = settings.read_text(encoding='utf-8')
    for key, value in [('op_mode', 'handheld'), ('pad_layout', 'touch')]:
        if not any(line.startswith(key + '\t') for line in text.splitlines()):
            text += f'\n{key}\t{value}\n'
    settings.write_text(text, encoding='utf-8')
    env['DM_GAMES_DIR'] = str(profile.parent)
    os.environ['DM_GAMES_DIR'] = env['DM_GAMES_DIR']
    game_profile = game.load(f'{title:016X}')
    version = facts['version']
    extracted = work / 'extract' / version
    if not (extracted / 'ExeFS/main').exists():
        extracted.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(nx), str(args.keys.resolve()), str(args.image.resolve()),
                        str(args.image.resolve()), str(extracted), '--app', f'{title:016x}'],
                       env=env, check=True)
    logs = work / 'logs'
    logs.mkdir(exist_ok=True)
    build.extract_aoc(nx, args.keys.resolve(), repo, work, title, family, logs)
    build.rewrite(Path(sys.executable), repo, extracted / 'ExeFS',
                  work / f'patched_{version}', env, logs, game_profile, provisional=True)
    game_profile = build.refine_after_rewrite(game_profile, extracted, work / f'patched_{version}')
    build.split_shaders(Path(sys.executable), repo, [extracted / 'RomFS'],
                        [extracted / 'ExeFS/main'], work / 'shader/pkg',
                        env, logs, game_profile, provisional=True)
    cuts = work / f'patched_{version}' / 'main.cuts.tsv'
    rows = [line for line in cuts.read_text().splitlines() if line.strip() and not line.startswith('#')]
    assert len(rows) == 1 and rows[0].startswith('0x4444dc\t') and 'frame limiter threshold' in rows[0], 'Expected validated 1.1.3 frame limiter cut'
    print(f'Local survey, merged extraction, rewrite and shader split complete: {work}', flush=True)


if __name__ == '__main__':
    main()
