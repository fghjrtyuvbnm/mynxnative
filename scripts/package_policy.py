"""Shared launcher policy for locally finalized and future external packages."""
import json
import plistlib
import zipfile

DEVICE_GYRO = dict(env='DM_PHONE_MOTION', kind='toggle', section='Controls',
    label='Use device gyroscope',
    note='Use this iPhone or iPad for motion even when a controller is connected. Turn off for automatic selection.',
    default='1', on='1', off='auto', level='basic')
DEVICE_GYRO_TSV = '\t'.join(('DM_PHONE_MOTION','toggle','1/auto','1','platform:ios','Controls',
    DEVICE_GYRO['label'],DEVICE_GYRO['note'],'level=basic'))


def install_launcher_policy(repo):
    path=repo/'dm/games/settings.tsv'
    text=path.read_text(encoding='utf-8')
    existing=[line for line in text.splitlines() if line.startswith('DM_PHONE_MOTION\t')]
    if existing and existing != [DEVICE_GYRO_TSV]:
        raise ValueError('Review the existing device-motion setting before replacing it')
    if not existing: path.write_text(text.rstrip()+'\n'+DEVICE_GYRO_TSV+'\n',encoding='utf-8')


def patch_ipa(source,destination,manifest_digest):
    """Change only the manifest binding and data-driven toggle in an unsigned IPA."""
    info_name='Payload/DmIOS.app/Info.plist'
    settings_name='Payload/DmIOS.app/dm/launcher.json'
    with zipfile.ZipFile(source) as src:
        if any('/_CodeSignature/' in n or n.endswith('embedded.mobileprovision') for n in src.namelist()):
            raise ValueError('Only unsigned IPAs may be updated locally')
        info=plistlib.loads(src.read(info_name))
        info['DMShaderCacheManifest']=manifest_digest
        settings=json.loads(src.read(settings_name)) if settings_name in src.namelist() else {'schema':1,'settings':[]}
        rows=settings['settings']; found=[i for i,r in enumerate(rows) if r['env']=='DM_PHONE_MOTION']
        if len(found)>1: raise ValueError('Duplicate device-motion settings')
        if found: rows[found[0]]=dict(DEVICE_GYRO)
        else:
            index=next((i for i,r in enumerate(rows) if r.get('section')=='Controls'),len(rows))
            rows.insert(index,dict(DEVICE_GYRO))
        updates={info_name:plistlib.dumps(info),settings_name:(json.dumps(settings,ensure_ascii=False,indent=1)+'\n').encode()}
        with zipfile.ZipFile(destination,'x',allowZip64=True) as dst:
            for item in src.infolist(): dst.writestr(item,updates.pop(item.filename,src.read(item.filename)))
            for name,payload in updates.items(): dst.writestr(name,payload,compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(destination) as check:
        if check.testzip(): raise ValueError('Updated IPA failed CRC validation')
        if plistlib.loads(check.read(info_name))['DMShaderCacheManifest']!=manifest_digest:
            raise ValueError('Updated IPA has the wrong manifest')
