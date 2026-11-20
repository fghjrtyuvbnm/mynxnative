import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ipa_crypto import transform
source,dest=map(Path,sys.argv[1:]);dest.mkdir()
for name in ('ZeldaBreathOfTheWild.ipa','game-data.json','shaders.pack'):
 p=source/name;out=dest/(name+'.enc');transform(p,out,bytes.fromhex(os.environ['BUILD_CIPHER_KEY']));assert out.stat().st_size==p.stat().st_size+36;p.unlink()
