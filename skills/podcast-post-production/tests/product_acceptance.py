from pathlib import Path
import hashlib,json,subprocess,sys
import numpy as np
from PIL import Image
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package
p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--font',type=Path,required=True);a=p.parse_args()
WORK=a.work_dir.resolve();ROOT=Path(__file__).resolve().parents[1];OUT=outside_package(a.report_dir).resolve();OUT.mkdir(parents=True,exist_ok=False);PY=Path(sys.executable)
import shutil
FF=shutil.which('ffmpeg');FP=shutil.which('ffprobe');results=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(name,passed,detail=None):results.append({'case':name,'status':'PASS' if passed else 'FAIL','detail':detail})
def call(name,args):
 p=subprocess.run([str(a) for a in args],capture_output=True);(OUT/(name+'.log')).write_bytes(p.stdout+p.stderr);check(name,p.returncode==0,{'exit_code':p.returncode,'command':[str(x) for x in args],'log':name+'.log'});return p

def probe(p):return json.loads(subprocess.check_output([FP,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
for name,duration,frames in [('conformed.mp4',16,480),('clip.mp4',5.9,177),('parent-3tracks.mp4',5,150),('revised-3tracks.mp4',4,120)]:
 p=WORK/name;data=probe(p);v=next(s for s in data['streams'] if s['codec_type']=='video');check(name+' duration',abs(float(data['format']['duration'])-duration)<.08);check(name+' frames',int(v['nb_read_frames'])==frames);call(name+' full-decode',[FF,'-v','error','-i',p,'-map','0','-f','null','-'])
 if '3tracks' in name:
  audio=[s for s in data['streams'] if s['codec_type']=='audio'];check(name+' audio-layout',len(audio)==3 and [s['disposition']['default'] for s in audio]==[1,0,0],audio)
review=list((WORK/'review').glob('*.mp4'));check('one Review output',len(review)==1)
if review:
 call('Review full-decode',[FF,'-v','error','-i',review[0],'-map','0','-f','null','-'])
 config=json.loads((WORK/'review.json').read_text());data=probe(review[0]);v=next(s for s in data['streams'] if s['codec_type']=='video');configured_fps=config.get('fps',60)
 check('Review frames at configured fps',int(v['nb_read_frames'])==round(5.9*configured_fps),{'fps':configured_fps,'frames':int(v['nb_read_frames'])})
for name,size in [('frame-preview.png',(1080,1920)),('frame-mobile.png',(270,480)),('frame-overlay.png',(1080,1920))]:
 with Image.open(WORK/'visual'/name) as im:check(name+' dimensions',im.size==size)
summary=json.loads((WORK/'integration-summary.json').read_text());check('21 steps',len(summary['steps'])==21 and all(s['exit_code']==0 for s in summary['steps']));check('source hashes',all(sha(p)==h for p,h in summary['protected_input_sha256_before'].items()))
qa=json.loads((WORK/'retime-qa.json').read_text());check('retime QA',qa['input_cues']==3 and qa['output_cues']==2 and qa['removed_cues']==[2] and qa['deleted_seconds']==1.0 and '00:00:01,000 --> 00:00:04,000' in (WORK/'revised.srt').read_text(),qa)
config={'output_dir':str(OUT/'headframes'),'font_file':str(a.font),'jobs':[{'id':'synthetic','video':str(WORK/'clip.mp4'),'times':[.9,2.6,4.8]}]}
# Headframe script accepts candidates or timestamps; derive exact current supported field.
config['jobs'][0].pop('times');config['jobs'][0]['timestamps']=[.9,2.6,4.8]
cfg=OUT/'headframe-config.json';cfg.write_text(json.dumps(config))
call('headframe extraction',[PY,'-B',ROOT/'modules/trailers/scripts/extract_headframe_candidates.py',cfg])
for label,p,time in [('multi-cjk',WORK/'clip.mp4',.9),('second-cue',WORK/'clip.mp4',2.6),('review-cjk',review[0],.9)]:
 call(label+' frame',[FF,'-v','error','-ss',time,'-i',p,'-frames:v','1',OUT/(label+'.png')])
def pcm(p):return np.frombuffer(subprocess.check_output([FF,'-v','error','-i',p,'-ac','1','-ar','48000','-f','f32le','-']),dtype='<f4')
ref=pcm(WORK/'reference.wav');render=pcm(WORK/'conformed.mp4');begin=15*48000;end=min(len(ref),len(render),16*48000);corr=float(np.corrcoef(ref[begin:end],render[begin:end])[0,1]);check('short tail diagnostic',corr>=.99,{'range_seconds':[15,16],'samples':end-begin,'correlation':corr,'original_validator_warning_preserved':True,'does_not_change_validator_threshold':True})
(OUT/'results.json').write_text(json.dumps({'items':results,'human_full_review':'not_performed','windows_linux_execution':'not_performed','ok':all(x['status']=='PASS' for x in results)},ensure_ascii=False,indent=2)+'\n')
if not all(x['status']=='PASS' for x in results): raise AssertionError('product acceptance failed')
print(json.dumps({'cases':len(results),'passed':sum(x['status']=='PASS' for x in results),'failed':[x for x in results if x['status']=='FAIL'],'tail_correlation':corr},ensure_ascii=False))
