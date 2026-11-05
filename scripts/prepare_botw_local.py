"""Prepare the user's merged Breath of the Wild XCI with version-derived settings."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TITLE = '01007EF00011E000'
VERSION = 'v786432'


def main():
    repo = Path(__file__).resolve().parents[1]
    root = Path('D:/Users/xly/Downloads/roms/switch')
    images = list(root.glob('*'+TITLE+'*.xci'))
    if len(images) != 1: raise ValueError('Expected one source XCI')
    source = images[0]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('work',type=Path)
    work = ap.parse_args().work.resolve()
    tools = root/'01008D7016438000-work/tools'
    env = dict(os.environ, DOTNET_ROOT=str(tools/'dotnet'), DOTNET_ROOT_X64=str(tools/'dotnet'),
               PATH=str(tools/'dotnet')+os.pathsep+os.environ['PATH'], GAME=TITLE, DM_GAME=TITLE,
               DM_GAMES_FIRST='1', DM_REWRITE_J='1', J='3', PYTHONUTF8='1',
               WORK=str(work/'tmp'), DM_ROOT=str(work))
    os.environ.update(env)
    sys.path[:0] = [str(repo/'dm/games'),str(repo/'dm/tools')]
    spec = importlib.util.spec_from_file_location('nsp_build',repo/'scripts/build_ipa_from_nsp.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    import game, profile_guess, nacp
    build.pg, build.nacp = profile_guess, nacp
    def remove_derived(path):
        path = Path(path).resolve()
        if path == work or not path.is_relative_to(work):
            raise ValueError('Refusing cleanup outside a derived game subdirectory')
        if path.is_file() or path.is_symlink(): path.unlink()
        elif path.exists(): shutil.rmtree(path)
    build.rmtree = remove_derived
    logs = work/'logs'; logs.mkdir(parents=True,exist_ok=True)
    build.PROG.mode = 'lines'; build.PROG.plan(4)
    extract = work/'extract'/VERSION
    romfs = extract/'RomFS'
    final_data = work/'ZeldaBreathOfTheWild-Data'
    if not romfs.is_dir() and (final_data/'romfs').is_dir(): romfs = final_data/'romfs'
    if not romfs.is_dir() and (final_data/'romfs.img').is_file(): romfs = final_data/'romfs.img'
    if not romfs.exists():
        extract.parent.mkdir(exist_ok=True)
        build.PROG.stage('extract merged release')
        build.run([tools/'nx_extract/nx_extract.exe', root.parent/'22.5.0/prod.keys',source,source,
                   extract,'--app',TITLE.lower()],logs/'extract.log',env=env)
    if nacp.version(extract/'control.nacp') != '1.6.0':
        raise ValueError('Unexpected XCI display version')
    family = {'base':source,'updates':[(786432,source)],'dlc':[(int(TITLE,16)+0x1001,196608,source),(int(TITLE,16)+0x1002,196608,source)]}
    aoc = final_data/'aoc'
    if not all((aoc/f'{i}.img').is_file() for i in (1,2)):
        aoc = build.extract_aoc(tools/'nx_extract/nx_extract.exe',root.parent/'22.5.0/prod.keys',repo,work,int(TITLE,16),family,logs)
    original = game.load(TITLE)
    pdir = work/'profile'/TITLE
    build.derive_profile(original,pdir,VERSION,extract,original.words('modules'))
    os.environ['DM_GAMES_DIR'] = env['DM_GAMES_DIR'] = str(pdir.parent)
    profile = game.load(TITLE)
    mismatch = build.build_mismatch(extract,VERSION,profile)
    if mismatch: raise ValueError(mismatch)
    patch = work/('patched_'+VERSION)
    build.rewrite(Path(sys.executable),repo,extract/'ExeFS',patch,env,logs,profile,provisional=True)
    profile = build.refine_after_rewrite(profile,extract,patch)
    original_run = build.run
    def run_scanner(cmd,*args,**kwargs):
        cmd = list(cmd)
        if len(cmd)>1 and Path(cmd[1]).name == 'shader_split.py':
            cmd[1] = repo/'scripts/split_windows_shaders.py'
        return original_run(cmd,*args,**kwargs)
    build.run = run_scanner
    build.split_shaders(Path(sys.executable),repo,[romfs],[extract/'ExeFS/main'],
                        work/'shader/pkg',env,logs,profile,provisional=True,dlc_roms=sorted(aoc.glob('*.img')))
    if '[RED]' in (logs/'shader_split.log').read_text(encoding='utf-8',errors='replace'):
        raise ValueError('Shader scan reported unreadable or unsupported content')
    rows = [line.split('\t') for line in (pdir/'shader_map.tsv').read_text().splitlines()
            if line and not line.startswith(('#','package\t'))]
    import romfs as image_reader
    resource_root=image_reader.Path(romfs) if romfs.is_file() else romfs
    resources = [p for p in resource_root.rglob('*') if p.is_file()]
    facts = dict(title=TITLE,version=VERSION,display='1.6.0',main=build.build_id(extract/'ExeFS/main'),
                 resource_count=len(resources),resource_bytes=sum(p.stat().st_size for p in resources),
                 shaders=len(rows),source=source.name,
                 dlc=[dict(index=int(p.stem),bytes=p.stat().st_size) for p in sorted(aoc.glob('*.img'))],
                 fps_target=profile.get('fps_target'),work=str(work))
    (work/'preparation.json').write_text(json.dumps(facts,indent=2)+'\n',encoding='utf-8')
    print('Local preparation complete:',json.dumps(facts),flush=True)


if __name__ == '__main__':
    main()
