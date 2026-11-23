"""Reconstruct canonical inputs from previously authenticated encrypted captures."""
from pathlib import Path
import hashlib,json,os,shutil,sys,tarfile

def main(repo,legacy,dest,archive):
 repo,legacy,dest,archive=map(lambda p:Path(p).resolve(),(repo,legacy,dest,archive))
 with tarfile.open(legacy/'meta.tar.xz') as tar:tar.extractall(legacy/'meta',filter='data')
 state=json.loads((legacy/'meta/build-state.json').read_bytes());key=state['key']
 dest.mkdir();old_map=None
 slots={'sentinels':['original'],'unicorn':['original'],'botw':['link','shader'],'octopath':['current','original'],'three-houses':['current'],'triangle':['current','original']}[key]
 for name in slots:
  with tarfile.open(legacy/(name+'.tar.xz')) as tar:
   for m in tar:
    if not m.isfile():continue
    path=m.name;out=None
    if '/pkg/' in path and path.endswith('.bin'):out=dest/'shader/pkg'/path.split('/pkg/',1)[1]
    elif path.endswith('/shader_map.tsv'):old_map=tar.extractfile(m).read()
    elif path.endswith('/pso_pairs.tsv'):out=dest/'shader/pso_pairs.tsv'
    elif path.startswith('patched_'+state['version']+'/') and not (name=='original' and key in ['octopath','triangle']):out=dest/path
    elif not (name=='original' and key in ['octopath','triangle']):
     if path.endswith('/ExeFS/main.npdm'):out=dest/'extract'/state['version']/'ExeFS/main.npdm'
     elif path.endswith('/control.nacp'):out=dest/'extract'/state['version']/'control.nacp'
     elif path.endswith('/icon.jpg'):out=dest/'extract'/state['version']/'icon.jpg'
     elif '/RomFS/' in path and path.split('/RomFS/',1)[1]==state['marker']:out=dest/'extract'/state['version']/'RomFS'/state['marker']
    if out is not None:
     assert out.resolve().is_relative_to(dest)
     out.parent.mkdir(parents=True,exist_ok=True)
     with tar.extractfile(m) as src,out.open('wb') as dst:shutil.copyfileobj(src,dst)
 current=(repo/'dm/games'/state['title']/'shader_map.tsv').read_text(encoding='utf-8')
 if old_map is None:previous=current
 else:
  try:previous=old_map.decode('utf-8')
  except UnicodeDecodeError:previous=old_map.decode('cp936')
 os.environ.update(GAME=state['title'],DM_GAME=state['title'])
 sys.path[:0]=[str(repo/'dm/gfx/tools'),str(repo/'dm/tools'),str(repo/'dm/games')]
 from remap import remap
 remap(dest/'shader',previous,current)
 assert state['main_build'] in (dest/('patched_'+state['version'])/'main.fixups.tsv').read_text()
 shutil.copyfile(legacy/'meta/game-assets.json',dest/'game-assets.json')
 shutil.copyfile(legacy/'meta/build-state.json',dest/'build-state.json')
 with tarfile.open(archive,'w:xz',preset=1) as tar:
  for p in sorted(dest.rglob('*')):
   if p.is_file():tar.add(p,p.relative_to(dest).as_posix(),recursive=False)
 print('Reused authenticated captures for',key,'and verified',state['shader_count'],'shader records',flush=True)

if __name__=='__main__':main(*sys.argv[1:])
