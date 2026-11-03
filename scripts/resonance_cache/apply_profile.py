"""Apply the reviewed HK-only additions to a fixed upstream revision."""
import pathlib
import shutil
import subprocess
import sys
from build_cache_launcher import SOURCE, BUILD, TITLE

def apply(repo):
    repo=pathlib.Path(repo).resolve()
    if subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()!=SOURCE:
        raise ValueError('Unexpected nxnative revision')
    src=pathlib.Path(__file__).resolve().parents[1]/'profiles'/TITLE
    dst=repo/'dm/games'/TITLE
    if src.is_dir():
        shutil.copytree(src,dst,dirs_exist_ok=True)
    else:
        subprocess.run(['git','-C',str(repo),'fetch','--depth=1','https://github.com/seedds/nxnative.git','309722488d994df048b5750f82ad13e451a0cac5'],check=True)
        subprocess.run(['git','-C',str(repo),'checkout','309722488d994df048b5750f82ad13e451a0cac5','--','dm/games/'+TITLE],check=True)
    # The PR predates the verified CopyStencilToLightingChannelsPS integer-output fix.
    # Carry its generated table only when every old fact and shader key agrees.
    jp=repo/'dm/games/0100606026F12000'
    rows=lambda p:{line for line in p.read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')}
    facts=rows(dst/'shader_facts.tsv');known=rows(jp/'shader_facts.tsv')
    manual=rows(jp/'shader_facts_manual.tsv')
    shader_keys=lambda p:{tuple(line.split('\t')[2:4]) for line in rows(p)}
    expected={'c254eaa40e0c4f1e\t{"fout":{"0":"uint"}}'}
    if manual!=expected or facts-known or known-facts not in (set(),expected):
        raise ValueError('Unexpected shader fact differences; review instead of inheriting them')
    if shader_keys(dst/'shader_map.tsv')!=shader_keys(jp/'shader_map.tsv'):
        raise ValueError('HK shader keys differ from the verified source of the integer output fact')
    shutil.copyfile(jp/'shader_facts_manual.tsv',dst/'shader_facts_manual.tsv')
    shutil.copyfile(jp/'shader_facts.tsv',dst/'shader_facts.tsv')
    p=repo/'dm/host/hle_uemalloc.c'; text=p.read_text(encoding='utf-8')
    if BUILD not in text:
        anchor='    { "84e182f72ee1da4f477804bd05b54c15", "FINAL FANTASY RESONANCE 1.0.1", UE5_6, 0x77c6210, 0x67df800, 0x137f0 },'
        if text.count(anchor)!=1: raise ValueError('Allocator table anchor changed')
        text=text.replace(anchor,anchor+'\n    { "'+BUILD+'", "FINAL FANTASY RESONANCE HK 1.0.1", UE5_6, 0x77c6210, 0x67df800, 0x137f0 },')
        p.write_text(text,encoding='utf-8',newline='\n')
    print('HK profile, verified integer shader output and build-gated allocator installed')

if __name__=='__main__': apply(sys.argv[1])
