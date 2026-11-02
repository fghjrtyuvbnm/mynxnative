"""Opt-in handheld and invisible touch controls for the four requested packages."""
from pathlib import Path
import hashlib,json,plistlib,shutil,zipfile

ALLOWED={'010016100A186000','010057D00B612000','0100346017304000','0100F0E0136BE000'}
NEW_UI_SHA='cc07a9289fa2a58057714f4c676ccd02f429412704378ac07831030f488cc1b0'
BASE_UI_SHA='6ee35d4e43eb1b13fa34c316682f567e799e8a0973954e2a4ef3736ef73fb66f'

def configure_profile(build, profile):
    if profile.id not in ALLOWED:
        raise ValueError('Touch-only build was not requested for this title')
    return build.set_keys(profile, {
        'op_mode':('handheld','start with the touchscreen available'),
        'pad_layout':('touch','start with direct touch and no virtual gamepad'),
    },'Touch-only input defaults')

def normalized_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def patch_ios_source(repo):
    config=Path(__file__).resolve().parents[1]
    source=config/'dm/ios/Sources'
    parts=sorted((config/'scripts/touch-ui').glob('DmGamepad.m.part*'))
    data=b''.join(p.read_bytes() for p in parts)
    if hashlib.sha256(data).hexdigest()!=NEW_UI_SHA:
        raise ValueError('UIKit source transport checksum mismatch')
    target=Path(repo)/'dm/ios/Sources'
    ui=target/'DmGamepad.m'
    if normalized_sha(ui) not in (BASE_UI_SHA,NEW_UI_SHA):
        raise ValueError('Unexpected UIKit source version; refusing to overwrite it')
    ui.write_bytes(data)
    for name in ['TouchLayoutPolicy.h']:
        if (source/name).resolve()!=(target/name).resolve():
            shutil.copyfile(source/name,target/name)
    project=Path(repo)/'dm/ios/project.yml'
    text=project.read_text(encoding='utf-8')
    if '        DMTouchOnly: true' not in text:
        anchor='        DMLanguage:'
        if anchor not in text:raise ValueError('Missing iOS Info.plist property anchor')
        text=text.replace(anchor,'        DMTouchOnly: true\n'+anchor,1)
        project.write_text(text,encoding='utf-8')

def verify_template(path):
    with zipfile.ZipFile(path) as archive:
        info=plistlib.loads(archive.read('Payload/DmIOS.app/Info.plist'))
        launcher=json.loads(archive.read('Payload/DmIOS.app/dm/launcher.json'))
        assert info.get('DMTouchOnly') is True,'Missing touch-only UIKit policy'
        assert next(r for r in launcher['settings'] if r['env']=='DM_OPMODE')['default']=='0','Launcher is not handheld by default'
