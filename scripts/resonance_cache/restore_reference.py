import os
"""Restore only authenticated link modules from existing private release assets."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen


def restore(work):
    config = work / 'reference-transfer.json'
    refreshed = os.environ.get('FFR_TRANSFER_REFRESH')
    if refreshed:
        config = Path(refreshed)
    if not config.is_file():
        return
    meta = json.loads(config.read_text())
    config.unlink()
    def fetch(item):
        index, row = item
        tail = work / 'reference-tail.part'
        if index == len(meta['parts']) - 1 and tail.is_file():
            with tail.open('rb') as f:
                if tail.stat().st_size != row['bytes'] or hashlib.file_digest(f, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Encrypted reference tail did not match its manifest')
            return tail
        url = row['url']
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.githubusercontent.com'):
            raise ValueError('Unexpected private asset host')
        target = work/f'reference-input-{index}'
        for attempt in range(5):
            try:
                with urlopen(url, timeout=90) as response, target.open('xb') as output:
                    shutil.copyfileobj(response, output, length=1024*1024)
                with target.open('rb') as stream:
                    if target.stat().st_size == row['bytes'] and hashlib.file_digest(stream,'sha256').hexdigest() == row['sha256']:
                        return target
                reason = 'integrity mismatch'
            except HTTPError as error:
                reason = f'HTTP {error.code}'
            except Exception as error:
                reason = type(error).__name__
            target.unlink(missing_ok=True)
            print(f'Private build input {index}, attempt {attempt + 1}: {reason}', flush=True)
            time.sleep(2 ** attempt)
        raise RuntimeError(f'Private build input {index} unavailable: {reason}')
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
