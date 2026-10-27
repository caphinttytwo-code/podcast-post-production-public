from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package
p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--font',type=Path);a=p.parse_args()
OUT=outside_package(a.report_dir).resolve();OUT.mkdir(parents=True,exist_ok=False)
ROOT=Path(__file__).resolve().parents[1]
FIX=OUT/'protection-fixtures-run02'
LOG=OUT/'protection-logs-run02';LOG.mkdir()
SYN=a.work_dir.resolve();PY=sys.executable;FF=shutil.which('ffmpeg')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class ProtectionViolation(RuntimeError):pass
from shared.test_steps import ControlFailed,protection_result
protected={};current_batch={};protected_batches={}
summary=json.loads((SYN/'integration-summary.json').read_text()) if (SYN/'integration-summary.json').exists() else {}
protected.update(summary.get('protected_input_sha256_before',{}))
def log(name, argv):
 inputs=[]
 script=str(argv[1]) if len(argv)>1 else ''
 if script.endswith(('render_podcast_edl.py',)):inputs=list(argv[2:4])
 elif script.endswith(('inventory_project.py','build_visuals.py','project_index.py','make_approval_sample.py')):
  inputs=[argv[2]] if script.endswith(('inventory_project.py','build_visuals.py','make_approval_sample.py')) else [argv[argv.index('--spec')+1]]
 for flag in ('--input','--edits','--source-video','--reference-audio'):
  if flag in argv:inputs.append(argv[argv.index(flag)+1])
 for item in inputs:
  if Path(item).is_file():current_batch.setdefault(str(Path(item).resolve()),sha(item))
 all_inputs={**protected,**current_batch}
 if any(not Path(path).is_file() or sha(path)!=h for path,h in all_inputs.items()):raise ProtectionViolation('Protected input changed before execution')
 p=subprocess.run([str(x) for x in argv],capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
 (LOG/f'{name}.stdout.txt').write_text(p.stdout)
 (LOG/f'{name}.stderr.txt').write_text(p.stderr)
 data={'exit_code':p.returncode,'argv':[str(x) for x in argv], 'stdout_log':f'protection-logs-run02/{name}.stdout.txt','stderr_log':f'protection-logs-run02/{name}.stderr.txt','error':p.stderr.strip()[-1200:]}
 changed=[path for path,h in all_inputs.items() if not Path(path).is_file() or sha(path)!=h]
 if changed:raise ProtectionViolation('Protected input changed: '+str(changed))
 if name.endswith('positive') and p.returncode:raise ControlFailed('Normal control failed: '+name+'; '+data['error'])
 return p,data
def result(case,status,**kw):
 return protection_result(case,status,**kw)
FIX.mkdir(exist_ok=True)
results=[]
from shared import environment
sourcev=SYN/'source.mp4';ref=SYN/'reference.wav'
src_hash=sha(sourcev) if sourcev.exists() else None;ref_hash=sha(ref) if ref.exists() else None

def batch_audio():
 # Audio render positive output, then in-place, hardlink and symlink aliases.
 force=FIX/'force'; force.mkdir(exist_ok=True)
 source=force/'source.wav'; shutil.copy2(SYN/'source.wav',source)
 edl=force/'audio-edl.json'; shutil.copy2(SYN/'audio-edl.json',edl)
 normal=force/'normal.wav'; before=sha(source)
 p,d=log('audio-force-positive',[PY,ROOT/'modules/audio-edit/scripts/render_podcast_edl.py',source,edl,normal]); d['source_sha256_before']=before; d['source_sha256_after']=sha(source); d['positive_output_exists']=normal.is_file(); results.append(result('audio-render normal distinct output control','PASS' if p.returncode==0 and normal.is_file() and before==sha(source) else 'FAIL',**d))
 for label, target in [('overwrite',source),('hardlink',force/'hardlink.wav'),('symlink',force/'symlink.wav')]:
  if label=='hardlink': os.link(source,target)
  if label=='symlink': target.symlink_to(source)
  pre=sha(source); target_pre=sha(target) if target.exists() else None
  p,d=log('audio-force-'+label,[PY,ROOT/'modules/audio-edit/scripts/render_podcast_edl.py',source,edl,target,'--force'])
  post=sha(source); target_post=sha(target) if target.exists() else None
  passed=p.returncode!=0 and pre==post and (target_pre is None or target_pre==target_post)
  results.append(result(f'audio-render force {label} alias rejection','PASS' if passed else 'FAIL',**d,source_sha256_before=pre,source_sha256_after=post,target_sha256_before=target_pre,target_sha256_after=target_post))


def batch_inventory():
 # Project inventory: valid result; JSON and TSV report names colliding with scanned config.
 inv=FIX/'inventory'; scan=inv/'scan'; scan.mkdir(parents=True,exist_ok=True)
 (scan/'fixture.wav').write_bytes((SYN/'source.wav').read_bytes())
 control_cfg=inv/'control.json'; control_out=inv/'control-out'
 control_cfg.write_text(json.dumps({'roots':[{'id':'s','path':str(scan)}],'output_dir':str(control_out),'hash_mode':'all'}))
 p,d=log('inventory-positive',[PY,ROOT/'modules/project-audit/scripts/inventory_project.py',control_cfg]); d['positive_json_exists']=(control_out/'inventory.json').is_file(); d['positive_tsv_exists']=(control_out/'inventory.tsv').is_file(); results.append(result('inventory normal output control','PASS' if p.returncode==0 and d['positive_json_exists'] and d['positive_tsv_exists'] else 'FAIL',**d))
 for label,filename in [('json','inventory.json'),('tsv','inventory.tsv')]:
  sub=inv/f'alias-{label}'; sub.mkdir(exist_ok=True); cfg=sub/filename
  cfg.write_text(json.dumps({'roots':[{'id':'s','path':str(scan)}],'output_dir':str(sub),'hash_mode':'all'}))
  pre=sha(cfg); p,d=log('inventory-alias-'+label,[PY,ROOT/'modules/project-audit/scripts/inventory_project.py',cfg]); post=sha(cfg)
  emitted=[(sub/'inventory.json').exists() and cfg.name!='inventory.json',(sub/'inventory.tsv').exists() and cfg.name!='inventory.tsv']
  passed=p.returncode!=0 and pre==post and not any(emitted)
  results.append(result(f'inventory {label} output alias config rejection','PASS' if passed else 'FAIL',**d,config_sha256_before=pre,config_sha256_after=post,other_output_created=any(emitted)))


def batch_acoustic():
 # Acoustic EDL: valid positive control and a work symlink escape.
 acoustic=ROOT/'modules/video-conform/scripts/build_acoustic_edl.py'; sourcev=SYN/'source.mp4'; ref=SYN/'reference.wav'; src_hash,ref_hash=sha(sourcev),sha(ref)
 acroot=FIX/'acoustic-positive'; acroot.mkdir(exist_ok=True)
 p,d=log('acoustic-positive',[PY,acoustic,'--source-video',sourcev,'--reference-audio',ref,'--project-root',acroot,'--job-id','positive','--skip-hashes']); d['manifest_exists']=(acroot/'manifests/positive.json').is_file(); results.append(result('acoustic EDL positive control','PASS' if p.returncode==0 and d['manifest_exists'] else 'FAIL',**d,source_sha256_before=src_hash,source_sha256_after=sha(sourcev),reference_sha256_before=ref_hash,reference_sha256_after=sha(ref)))
 acroot=FIX/'acoustic-symlink'; acroot.mkdir(exist_ok=True); outside=FIX/'acoustic-outside'; outside.mkdir(exist_ok=True); (acroot/'work').symlink_to(outside,target_is_directory=True)
 p,d=log('acoustic-work-symlink',[PY,acoustic,'--source-video',sourcev,'--reference-audio',ref,'--project-root',acroot,'--job-id','linked','--skip-hashes']); d['outside_entries']=sorted(x.name for x in outside.iterdir()); passed=p.returncode!=0 and not d['outside_entries'] and not (acroot/'manifests').exists(); results.append(result('acoustic work/cache symlink escape rejection','PASS' if passed else 'FAIL',**d,source_sha256_before=src_hash,source_sha256_after=sha(sourcev),reference_sha256_before=ref_hash,reference_sha256_after=sha(ref)))


def batch_sample():
 # Sample renderer: safe positive control and unsafe sample IDs; positive uses synthetic media only.
 manifest=SYN/'conform/manifests/synthetic.json'; sample=ROOT/'modules/video-conform/scripts/make_approval_sample.py'; sidroot=FIX/'samples'; sidroot.mkdir(exist_ok=True)
 p,d=log('approval-sample-positive',[PY,sample,manifest,'--output-dir',sidroot/'safe','--sample-id','safe','--pre','5','--post','7','--max-duration','12']); d['sample_exists']=(sidroot/'safe/safe-approval-sample.mp4').is_file(); results.append(result('approval sample normal ID control','PASS' if p.returncode==0 and d['sample_exists'] else 'FAIL',**d,source_sha256_before=src_hash,source_sha256_after=sha(sourcev),reference_sha256_before=ref_hash,reference_sha256_after=sha(ref)))
 for i,bad in enumerate([str(FIX/'abs-escape'),'../traversal']):
  before=set(str(x.relative_to(sidroot)) for x in sidroot.rglob('*')); p,d=log(f'approval-sample-bad-id-{i}',[PY,sample,manifest,'--output-dir',sidroot/f'bad-{i}','--sample-id',bad,'--pre','5','--post','7','--max-duration','12']); after=set(str(x.relative_to(sidroot)) for x in sidroot.rglob('*')); passed=p.returncode!=0 and before==after; results.append(result(f'approval sample rejects unsafe ID {i+1}','PASS' if passed else 'FAIL',**d,no_paths_created=before==after,source_sha256_before=src_hash,source_sha256_after=sha(sourcev)))


def batch_retime():
 # Retime SRT: successful output then temp-file collision with source.
 retime=ROOT/'modules/locked-revision/scripts/retime_srt.py'; rt=FIX/'retime'; rt.mkdir(exist_ok=True)
 inp=rt/'source.srt'; inp.write_text('1\n00:00:00,000 --> 00:00:01,000\n合成素材\n'); edits=rt/'no-edits.json'; edits.write_text('{"deletions": []}')
 p,d=log('retime-positive',[PY,retime,'--input',inp,'--edits',edits,'--output',rt/'clean.srt','--report',rt/'clean-report.json']); results.append(result('retime normal output control','PASS' if p.returncode==0 and (rt/'clean.srt').is_file() else 'FAIL',**d,input_sha256_before=sha(inp),input_sha256_after=sha(inp)))
 tmpin=rt/'.aliased.srt.tmp'; tmpin.write_text(inp.read_text()); before=sha(tmpin); p,d=log('retime-temp-alias',[PY,retime,'--input',tmpin,'--edits',edits,'--output',rt/'aliased.srt','--report',rt/'aliased-report.json']); passed=p.returncode!=0 and sha(tmpin)==before and not (rt/'aliased.srt').exists(); results.append(result('retime temporary file cannot overwrite input','PASS' if passed else 'FAIL',**d,input_sha256_before=before,input_sha256_after=sha(tmpin),output_absent=not (rt/'aliased.srt').exists()))


def batch_visual():
 # Subtitle visual assets: positive outside package then attempted output inside package; package tree checked unchanged.
 visual=ROOT/'modules/trailers/scripts/build_visuals.py'; vconf=json.loads((SYN/'visual.json').read_text()); vconf['output_dir']=str(FIX/'visual-good'); vcfg=FIX/'visual-good.json'; vcfg.write_text(json.dumps(vconf)); p,d=log('visual-positive',[PY,visual,vcfg]); d['cover_exists']=(FIX/'visual-good/cover.jpg').is_file(); results.append(result('subtitle/visual asset normal output control','PASS' if p.returncode==0 and d['cover_exists'] else 'FAIL',**d))
 def package_tree():
  return {str(x.relative_to(ROOT)):sha(x) for x in ROOT.rglob('*') if x.is_file() and '__pycache__' not in x.parts}
 pre_tree=package_tree(); badcfg=dict(vconf); badcfg['output_dir']=str(ROOT/'modules/trailers/references'); bcfg=FIX/'visual-inside-package.json'; bcfg.write_text(json.dumps(badcfg)); p,d=log('visual-inside-package',[PY,visual,bcfg]); post_tree=package_tree(); unchanged=pre_tree==post_tree; passed=p.returncode!=0 and unchanged; results.append(result('subtitle visual assets reject package destination','PASS' if passed else 'FAIL',**d,package_tree_unchanged=unchanged,files_before=len(pre_tree),files_after=len(post_tree)))


def batch_index():
 # Project index: valid identity, then declared-hash mismatch.
 index=ROOT/'scripts/project_index.py'; idxdir=FIX/'index'; idxdir.mkdir(exist_ok=True); asset=idxdir/'synthetic.wav'; asset.write_bytes((SYN/'source.wav').read_bytes()); actual=sha(asset)
 def spec(h): return {'workflow':'audio-edit','module_version':'test-fixture-v1','inputs':[{'role':'source','path':str(asset),'sha256':h}], 'artifacts':[]}
 good=idxdir/'good.json'; good.write_text(json.dumps(spec(actual))); p,d=log('index-positive',[PY,index,'--spec',good,'--output',idxdir/'good-index.json']); results.append(result('project index positive hash control','PASS' if p.returncode==0 and (idxdir/'good-index.json').is_file() else 'FAIL',**d,input_sha256=actual))
 bad=idxdir/'bad.json'; bad.write_text(json.dumps(spec('0'*64))); p,d=log('index-bad-hash',[PY,index,'--spec',bad,'--output',idxdir/'bad-index.json']); passed=p.returncode!=0 and not (idxdir/'bad-index.json').exists() and sha(asset)==actual; results.append(result('project index rejects declared hash mismatch','PASS' if passed else 'FAIL',**d,input_sha256_before=actual,input_sha256_after=sha(asset),output_absent=not (idxdir/'bad-index.json').exists()))


def batch(name,feature,needs,count,action):
 current_batch.clear()
 start=len(results);gate=environment.inspect(*feature.split(':',1)[:1],feature=feature.split(':',1)[1],font=a.font if feature.startswith('trailers:') else None) if feature else None
 status='BLOCKED' if gate and not gate['ok'] else 'NOT RUN' if any(not (SYN/p).exists() for p in needs) else None
 reason=gate['missing'] if status=='BLOCKED' else [p for p in needs if not (SYN/p).exists()]
 if status:
  for i in range(count):results.append(result(name+f' prerequisite {i+1}',status,reason=reason))
  return
 try:
  action()
  for row in results[start:]:row['feature']=feature
 except Exception as exc:
  status='BLOCKED' if isinstance(exc,OSError) and getattr(exc,'winerror',None)==1314 else 'FAIL'
  if len(results)<start+count:results.append(result(name+' stopped',status,error=str(exc),feature=feature))
  while len(results)<start+count:results.append(result(name+f' not run {len(results)-start+1}','NOT RUN',reason='Normal control/fixture/protection prerequisite failed',feature=feature))
 finally:
  protected_batches[name]={'before':dict(current_batch),'end':{path:sha(path) if Path(path).is_file() else None for path in current_batch}}
batch('audio','audio-edit:basic',['source.wav', 'audio-edl.json'],4,batch_audio)
batch('inventory','project-audit:inventory',['source.wav'],3,batch_inventory)
batch('acoustic','video-conform:full',['source.mp4', 'reference.wav'],2,batch_acoustic)
batch('sample','video-conform:full',['conform/manifests/synthetic.json'],3,batch_sample)
batch('retime',None,[],2,batch_retime)
batch('visual','trailers:images',['visual.json', 'synthetic-photo.png'],2,batch_visual)
batch('index',None,['source.wav'],2,batch_index)
(OUT/'source-protection.json').write_text(json.dumps({'before':protected,'final':{path:sha(path) if Path(path).is_file() else None for path in protected},'batches':{name:{**record,'final':{path:sha(path) if Path(path).is_file() else None for path in record['before']}} for name,record in protected_batches.items()}},indent=2))
(OUT/'protection-results-run02.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(results),'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),'results':str(OUT/'protection-results-run02.json')},ensure_ascii=False))

raise SystemExit(any(x['status']!='PASS' for x in results))
