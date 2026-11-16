"""Encrypt/decrypt build files with streaming AES-256-GCM; never print keys."""
import argparse
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b'NXGCM001'


def transform(source, destination, key, decrypt=False):
    source, destination = Path(source), Path(destination)
    if len(key) != 32:
        raise ValueError('Expected a 32-byte AES key')
    if source.resolve() == destination.resolve():
        raise ValueError('Input and output must differ')
    temporary = None
    try:
        with source.open('rb') as incoming:
            if decrypt:
                if incoming.read(8) != MAGIC:
                    raise ValueError('Invalid encrypted file header')
                nonce = incoming.read(12)
                size = source.stat().st_size - 36
                if size < 0:
                    raise ValueError('Truncated encrypted file')
                incoming.seek(-16, 2)
                tag = incoming.read(16)
                incoming.seek(20)
                worker = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            else:
                nonce = os.urandom(12)
                worker = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
                size = source.stat().st_size
            worker.authenticate_additional_data(MAGIC)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                if not decrypt:
                    output.write(MAGIC + nonce)
                remaining = size
                while remaining:
                    chunk = incoming.read(min(8 * 1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('Truncated input')
                    output.write(worker.update(chunk))
                    remaining -= len(chunk)
                output.write(worker.finalize())
                if not decrypt:
                    output.write(worker.tag)
            os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['encrypt', 'decrypt'])
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--key-file', help='Hex key file; otherwise BUILD_CIPHER_KEY environment')
    args = parser.parse_args()
    raw = Path(args.key_file).read_text().strip() if args.key_file else os.environ['BUILD_CIPHER_KEY']
    transform(args.source, args.destination, bytes.fromhex(raw), args.mode == 'decrypt')
