"""Compile a registered game runtime and complete shader pack on Apple Silicon."""
from pathlib import Path
import hashlib,importlib,json,os,plistlib,shutil,subprocess,sys,tarfile,zipfile

def choose_scheme(project,display,title):
 paths=list((project/'DmIOS.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'))
 matches=[p.stem for p in paths if p.stem.endswith('('+title+')')]
 assert len(matches)==1,('Expected one generated game scheme',matches)
 return matches[0]

def main(repo,archive,work,out):
 repo,archive,work,out=map(lambda p:Path(p).resolve(),(repo,archive,work,out))
 work.mkdir();out.mkdir()
 with tarfile.open(archive) as tar:tar.extractall(work,filter='data')
 state=json.loads((work/'build-state.json').read_bytes());title=state['title'];chain=state['chain']
 assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==state['source_commit']
 os.environ.update(GAME=title,DM_GAME=title)
 sys.path[:0]=[str(repo/p) for p in ('scripts','dm/tools','dm/games','dm/gfx/tools')]
 build=importlib.import_module('build_ipa_from_nsp');g=importlib.import_module('game').load(title)
 assert build.chain_of(repo)==chain
 build.PROG.mode='lines';build.PROG.plan(3)
 logs=work/'logs';logs.mkdir();(work/'tmp').mkdir()
 env=dict(os.environ,J='6',WORK=str(work/'tmp'),DM_ROOT=str(work))
 patched=work/('patched_'+state['version']);extract=work/'extract'/state['version']
 assert state['main_build'] in (patched/'main.fixups.tsv').read_text()
 ios=build.build_shaders(Path(sys.executable),repo,work/'shader',repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate',env,logs,g,pull=True)
 lib=build.shader_lib.view(ios/('b-'+chain));profile=repo/'dm/games'/title
 stamp=dict(line.split('\t',1) for line in (lib/'inputs.tsv').read_text().splitlines() if line and not line.startswith('#'))
 count=0
 for line in (profile/'shader_map.tsv').read_text().splitlines():
  if not line or line.startswith(('#','package\t')):continue
  pkg,index,stage,key,*_=line.split('\t');meta=json.loads((lib/(key+'_b.json')).read_text())
  assert (lib/(key+'_b.metallib')).is_file() or (stage=='geometry' and 'gs_slice' in meta),(stage,key)
  count+=1
 assert count==state['shader_count']
 manifest=dict(format_version=1,identity=dict(title_id=title,main_build=state['main_build'],shader_chain=chain,shader_inputs=stamp['inputs']),files=json.loads((work/'game-assets.json').read_bytes()))
 with (out/'shaders.pack').open('xb') as stream:
  stream.write(b'FFRSMSL1')
  for p in sorted(lib.iterdir(),key=lambda p:p.name):
   if p.suffix not in ('.json','.metallib','.tsv'):continue
   raw=p.read_bytes();stream.write(raw)
   manifest['files'].append(dict(path='msl/b-'+chain+'/'+p.name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
 raw=json.dumps(manifest,separators=(',',':')).encode();(out/'game-data.json').write_bytes(raw)
 # These files form a recoverable checkpoint even if native compilation fails.
 print('Completed shader checkpoint:',count,'shader keys;', (out/'shaders.pack').stat().st_size,'bytes',flush=True)
 derived=work/'xcode-dd'
 env.update(W=str(work/'ipa'),PATCHED=str(patched),ROMFS=str(extract/'RomFS'),MSL_IOS=str(ios),
  GFXAPI='nvn',FONT_PY=sys.executable,DM_DISPLAY_NAME=state['display'],DM_BUNDLE_ID=state['bundle'],DM_APP_VERSION=state['app_version'],
  DM_LANG=state['defaults'].get('DM_LANG','zh-Hans'),DM_PSO_GPUS='none',DM_ENTITLEMENTS='',DM_ICON=str(extract/'icon.jpg'),
  AOC='',DM_COPY_ROMFS='NO',DM_XCODE_DERIVED_DATA=str(derived))
 def run(*args):subprocess.run(list(map(str,args)),env=env,check=True)
 run('bash',repo/'dm/ios/tools/build_ipa.sh','--prepare-xcode')
 project=work/'ipa/xcode';plist=project/'Gen/Info.plist';info=plistlib.loads(plist.read_bytes())
 info.update(DMTabletPad=state['tablet'],DMExternalGameData=True,DMExternalDataVersion=1,DMLocalDataManagement=True,
  DMExternalDataIdentity=manifest['identity'],DMExternalRomFSMarker=state['marker'],DMShaderCacheManifest=hashlib.sha256(raw).hexdigest(),
  LSSupportsOpeningDocumentsInPlace=True,UIFileSharingEnabled=True)
 plist.write_bytes(plistlib.dumps(info))
 settings_path=project/'Gen/dm/launcher.json';settings=json.loads(settings_path.read_text());rows={r['env']:r for r in settings['settings']}
 for name,value in state['defaults'].items():
  if name in rows:rows[name]['default']=value
 if state['key']=='botw':
  expected={'DM_OPMODE':'0','DM_SCREEN_ASPECT':'0','DM_RENDER_SCALE':'1.0','DM_FPS_TARGET':'30','DM_PICTURE_FIT':'fit'}
  assert rows['DM_RENDER_SCALE']['base']['handheld']==[1280,720]
  for name,value in expected.items():assert rows[name]['default']==value
  rows['DM_LANG']['options']=state['language_options']
 settings_path.write_text(json.dumps(settings,separators=(',',':')))
 run('xcodebuild','-project',project/'DmIOS.xcodeproj','-scheme',choose_scheme(project,state['display'],title),'-configuration','Release',
  '-destination','generic/platform=iOS','-derivedDataPath',derived,'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=',
  'DM_COPY_GAME_RESOURCES=NO','DM_XCODE_OUTPUT_ROOT='+str(derived),'SYMROOT='+str(derived/'Build/Products'),
  'OBJROOT='+str(derived/'Build/Intermediates.noindex'),'build')
 app='Payload/DmIOS.app/';skip=[v for n in ('_CodeSignature','embedded.mobileprovision','romfs','romfs.img','msl','aoc') for v in ('--skip',app+n)]
 run(sys.executable,repo/'dm/ios/tools/pack_ipa.py',out/'game.ipa',*skip,app.rstrip('/')+'='+str(derived/'Build/Products/Release-iphoneos/DmIOS.app'))
 with zipfile.ZipFile(out/'game.ipa') as z:
  info=plistlib.loads(z.read(app+'Info.plist'))
  assert z.testzip() is None and info['DTSDKName']=='iphoneos27.2' and info['DMExternalDataIdentity']==manifest['identity']
  assert info['DMCommit'].startswith(state['source_commit'][:12]) and info['CFBundleIdentifier']==state['bundle']
 for temporary in (work/'shader',derived):
  assert temporary.is_relative_to(work);shutil.rmtree(temporary)
 print('Finished',state['key'],count,'shaders; unsigned external-data IPA validated',flush=True)
 build.PROG.close()

if __name__=='__main__':main(*sys.argv[1:])
