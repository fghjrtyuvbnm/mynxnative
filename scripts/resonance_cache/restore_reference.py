"""Restore only authenticated link modules from existing private release assets."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.parse import urlsplit
from urllib.request import urlopen


def restore(work):
    config = work / 'reference-transfer.json'
    if not config.is_file():
        return
    meta = json.loads(config.read_text())
    config.unlink()
    def fetch(item):
        index, row = item
        url = row['url']
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.githubusercontent.com'):
            raise ValueError('Unexpected private asset host')
        target = work/f'reference-input-{index}'
        try:
            with urlopen(url, timeout=90) as response, target.open('xb') as output:
                shutil.copyfileobj(response, output, length=1024*1024)
        except Exception:
            raise RuntimeError(f'Private build input {index} is unavailable or its grant expired') from None
        with target.open('rb') as stream:
            if target.stat().st_size != row['bytes'] or hashlib.file_digest(stream,'sha256').hexdigest() != row['sha256']:
                raise ValueError(f'Private build input {index} integrity mismatch')
        return target
    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(fetch, enumerate(meta['parts'])))
    archive = work/'reference-input.tar.gz'
    with archive.open('xb') as out:
        for p in files:
            with p.open('rb') as f: shutil.copyfileobj(f,out,length=1024*1024)
            p.unlink()
    expected = {x['path']: x for x in meta['files']}
    actual = set()
    with tarfile.open(archive,'r|gz') as tar:
        for m in tar:
            if m.name not in expected:
                continue
            row = expected[m.name]
            p = Path(m.name)
            if not m.isfile() or m.size != row['bytes'] or p.is_absolute() or '..' in p.parts or m.name in actual:
                raise ValueError('Unexpected linked module entry')
            data = tar.extractfile(m).read()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('Linked module digest mismatch')
            dest = work/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f: f.write(data)
            actual.add(m.name)
    archive.unlink()
    if actual != set(expected):
        raise ValueError('Missing verified linked module')
    print(f'Restored {len(actual)} verified link files from scoped private release downloads',flush=True)
