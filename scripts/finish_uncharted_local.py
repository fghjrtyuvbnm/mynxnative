"""Decrypt the cloud template and add complete local resources, preserving app modes."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import struct
import zipfile

from ipa_crypto import transform


def finish(encrypted, work, keyfile, output):
    output = output.resolve()
    if output.exists():
        raise ValueError('Output already exists; choose a new filename')
    template = work / 'UnchartedWatersIV-template.ipa'
    transform(encrypted, template, bytes.fromhex(keyfile.read_text().strip()), True)
    root = 'Payload/DmIOS.app/'
    romfs = work / 'extract/v131072/RomFS'
    files = sorted(path for path in romfs.rglob('*') if path.is_file())
    if not files or not (romfs / 'res/GlobalConfig.ktsl2gcbin').is_file():
        raise ValueError('Complete local RomFS is unavailable')
    partial = output.with_suffix('.ipa.partial')
    if partial.exists():
        raise ValueError('Partial output already exists; inspect it first')
    with zipfile.ZipFile(template) as source, zipfile.ZipFile(partial, 'w', allowZip64=True) as destination:
        if source.testzip() is not None:
            raise ValueError('Template ZIP CRC mismatch')
        info = plistlib.loads(source.read(root + 'Info.plist'))
        if info['CFBundleIdentifier'] != 'org.nxnative.0100f0e0136be000':
            raise ValueError('Wrong app bundle')
        executable = root + info['CFBundleExecutable']
        header = source.read(executable)[:8]
        if struct.unpack('<II', header) != (0xFEEDFACF, 0x0100000C):
            raise ValueError('App executable is not arm64 Mach-O')
        for entry in source.infolist():
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe template path')
            if entry.filename.startswith(root + 'romfs/') or entry.filename in (root + 'romfs.img', root + 'romfs.id'):
                continue
            if entry.is_dir():
                destination.writestr(entry, b'')
            else:
                with source.open(entry) as incoming, destination.open(entry, 'w') as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 8 * 1024 * 1024)
        for path in files:
            entry = zipfile.ZipInfo(root + 'romfs/' + path.relative_to(romfs).as_posix())
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_STORED
            entry.file_size = path.stat().st_size
            with path.open('rb') as incoming, destination.open(entry, 'w', force_zip64=entry.file_size >= 2**31) as outgoing:
                shutil.copyfileobj(incoming, outgoing, 8 * 1024 * 1024)
    with zipfile.ZipFile(partial) as package:
        if package.testzip() is not None:
            raise ValueError('Final IPA ZIP CRC mismatch')
        if not (package.getinfo(executable).external_attr >> 16) & 0o111:
            raise ValueError('App executable lost Unix execute mode')
        for path in files:
            name = root + 'romfs/' + path.relative_to(romfs).as_posix()
            if package.getinfo(name).file_size != path.stat().st_size:
                raise ValueError('Final resource size mismatch')
    partial.rename(output)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'title_id': '0100F0E0136BE000', 'version': '1.0.2', 'romfs_files': len(files),
              'bytes': output.stat().st_size, 'sha256': digest, 'zip_crc_verified': True,
              'signed': False, 'frame_rate_patch': False, 'device_runtime_tested': False}
    output.with_suffix('.verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('encrypted', type=Path)
    parser.add_argument('work', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    args = parser.parse_args()
    finish(args.encrypted, args.work, args.key_file, args.output)
