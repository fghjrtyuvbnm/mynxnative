"""Read NIS offline shader inputs without changing the pinned upstream translator.

FAFULLFS layout reference: HybridEidolon/makaikit fafullfs/src/lib.rs.
YKCMP type 7 and NMPL descriptors are verified against the local input lengths.
"""
import re
import struct
import sys
import zlib
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'dm/gfx/tools')]
import shader_split as upstream

MAGIC = re.compile(b'NMPL_NVN..SHADER', re.DOTALL)
ORIGINAL_BLOB = upstream.scan_blob
ORIGINAL_FILE = upstream.scan_file_in


def scan_nmpl(data, label):
    found = []
    for match in MAGIC.finditer(data):
        at = match.start()
        if at + 0x30 > len(data):
            raise ValueError('Truncated NMPL descriptor')
        head, co, ko, reflection, cn, kn, _, _ = struct.unpack_from('<8I', data, at + 16)
        if head != 0x30 or co != head + reflection or ko != co + cn or cn < 0x760 or kn < 0x34 or at + ko + kn > len(data):
            raise ValueError('Invalid NMPL ranges')
        ctl, code = data[at + co:at + co + cn], data[at + ko:at + ko + kn]
        stage = upstream.glslc_stage(ctl, code)
        if not stage or upstream.check(label, stage, ctl, code):
            raise ValueError('Invalid NMPL control/code pair')
        found.append((f'{label}#NMPL@{at:#x}', stage, ctl, code))
    return found


def decode_effect(data):
    if data[:12] != struct.pack('<3I', 1, 0xffffffff, 12) or data[12:20] != b'YKCMP_V1':
        return None
    if len(data) < 32:
        raise ValueError('Truncated YKCMP header')
    variant, stored, raw_size = struct.unpack_from('<3I', data, 20)
    if variant != 7 or stored + 12 != len(data) or raw_size > 512 * 1024 * 1024:
        raise ValueError('Unsupported YKCMP variant or invalid lengths')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(data[32:], raw_size + 1)
    if len(raw) != raw_size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('YKCMP zlib length/stream mismatch')
    if not raw.startswith(b'NMPL_FX_SHADERDT'):
        return None
    return raw


def effect_members(path):
    with open(path, 'rb') as stream:
        length = Path(path).stat().st_size
        header = stream.read(40)
        if len(header) != 40 or header[:8] != b'FAFULLFS':
            raise ValueError('Invalid FAFULLFS header')
        _, count, _, names_at, names_size, table_at = struct.unpack('<8sIIQQQ', header)
        if names_size > 64 * 1024 * 1024 or max(names_at + names_size, table_at + count * 48) > length:
            raise ValueError('FAFULLFS table outside archive')
        stream.seek(names_at); names = stream.read(names_size)
        stream.seek(table_at); table = stream.read(count * 48)
        for index in range(count):
            _, name_at, _, size, offset, _ = struct.unpack_from('<6Q', table, index * 48)
            if name_at >= len(names) or offset + size > length:
                raise ValueError('FAFULLFS member outside archive')
            end = names.find(b'\0', name_at)
            if end <= name_at:
                raise ValueError('Invalid FAFULLFS member name')
            name = names[name_at:end].decode('utf-8')
            stream.seek(offset); head = stream.read(min(size, 32))
            if head[:12] != struct.pack('<3I', 1, 0xffffffff, 12) or head[12:20] != b'YKCMP_V1':
                continue
            if size > 512 * 1024 * 1024:
                raise ValueError('Effect input exceeds decode budget')
            stream.seek(offset)
            if struct.unpack_from('<I', head, 20)[0] != 7 and not name.lower().endswith('.fxdat'):
                continue
            raw = decode_effect(stream.read(size))
            if raw is None and name.lower().endswith('.fxdat'):
                raise ValueError('Unrecognized effect payload')
            if raw is not None:
                yield name, raw


def scan_blob(data, label, found, depth=0, left=None):
    found.extend(scan_nmpl(data, label))
    return ORIGINAL_BLOB(data, label, found, depth, left)


def scan_file(args):
    path, label = args[:2]
    with open(path, 'rb') as stream:
        head = stream.read(8)
    if head != b'FAFULLFS':
        return ORIGINAL_FILE(args)
    found = []
    for name, raw in effect_members(path):
        found.extend(scan_nmpl(raw, f'/{label}/{name}'))
    return label, upstream.uniq_keys(found), upstream.var_pairs(found), {}


upstream.scan_blob = scan_blob
upstream.scan_file_in = scan_file

if __name__ == '__main__':
    upstream.main()
