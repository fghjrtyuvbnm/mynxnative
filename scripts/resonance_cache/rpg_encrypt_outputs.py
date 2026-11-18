"""Seal each completed output directly, without a second plaintext tar copy."""
import os
from pathlib import Path
import sys

def seal(source, destination, key, transform):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    names=('game.ipa','game-data.json','shaders.pack')
    assert source != destination
    assert all((source/name).is_file() for name in names)
    destination.mkdir(parents=True,exist_ok=True)
    for name in names:
        original=source/name
        encrypted=destination/(name+'.enc')
        transform(original,encrypted,key)
        assert encrypted.stat().st_size==original.stat().st_size+36
        original.unlink()
        print('Encrypted',name,encrypted.stat().st_size,'bytes',flush=True)

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from ipa_crypto import transform
    seal(sys.argv[1],sys.argv[2],bytes.fromhex(os.environ['BUILD_CIPHER_KEY']),transform)
