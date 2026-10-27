"""28 artifact assertions, independently gated by actual prerequisites."""
from pathlib import Path
import argparse,json,subprocess,sys,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package,sha256
from shared.test_steps import Steps
p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--font',type=Path);a=p.parse_args()
W=a.work_dir.resolve();R=Path(__file__).resolve().parents[1];O=outside_package(a.report_dir);O.mkdir(parents=True,exist_ok=False)
s=Steps(O,font=a.font);FF=shutil.which('ffmpeg') or 'ffmpeg';FP=shutil.which('ffprobe') or 'ffprobe'
def require(value,message):
 if not value:raise AssertionError(message)
 return True

def probe(path):return json.loads(subprocess.check_output([FP,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)]))
for name,duration,frames,feature in [('conformed.mp4',16,480,'video-conform:full'),('clip.mp4',5.9,177,'trailers:full'),('parent-3tracks.mp4',5,150,'locked-revision:full'),('revised-3tracks.mp4',4,120,'locked-revision:full')]:
 path=W/name
 s.run(name+' duration',needs=[path],feature=feature,action=lambda _,path=path,d=duration:require(abs(float(probe(path)['format']['duration'])-d)<.08,'Duration'))
 s.run(name+' frames',needs=[path],feature=feature,action=lambda _,path=path,n=frames:require(int(next(x for x in probe(path)['streams'] if x['codec_type']=='video')['nb_read_frames'])==n,'Frames'))
 s.run(name+' full-decode',[FF,'-v','error','-i',path,'-map','0','-f','null','-'],needs=[path],feature=feature)
 if '3tracks' in name:
  def layout(_,path=path):
   tracks=[x for x in probe(path)['streams'] if x['codec_type']=='audio'];return require(len(tracks)==3 and [x['disposition']['default'] for x in tracks]==[1,0,0],'Audio layout')
  s.run(name+' audio-layout',needs=[path],feature=feature,action=layout)
reviews=list((W/'review').glob('*.mp4'));review=reviews[0] if reviews else W/'review/missing.mp4'
s.run('one Review output',needs=[W/'review'],action=lambda _:require(len(reviews)==1,'Review output count'))
s.run('Review full-decode',[FF,'-v','error','-i',review,'-map','0','-f','null','-'],needs=[review],feature='locked-revision:full')
def review_frames(_):
 config=json.loads((W/'review.json').read_text());frames=int(next(x for x in probe(review)['streams'] if x['codec_type']=='video')['nb_read_frames']);fps=config.get('fps',60);require(frames==round(5.9*fps),'Review frames');return {'fps':fps,'frames':frames}
s.run('Review frames at configured fps',needs=[review,W/'review.json'],feature='locked-revision:full',action=review_frames)
for name,size in [('frame-preview.png',(1080,1920)),('frame-mobile.png',(270,480)),('frame-overlay.png',(1080,1920))]:
 def image(_,name=name,size=size):
  from PIL import Image
  with Image.open(W/'visual'/name) as im:return require(im.size==size,'Image dimensions')
 s.run(name+' dimensions',needs=[W/'visual'/name],feature='trailers:images',action=image)
summary=json.loads((W/'integration-summary.json').read_text());s.by.update({x['step']:x for x in summary['steps']})
s.run('21 steps',needs=[W/'integration-summary.json'],after=[x['step'] for x in summary['steps']],action=lambda _:require(len(summary['steps'])==21 and all(x['exit_code']==0 for x in summary['steps']),'21 original production steps'))
s.run('source hashes',action=lambda _:require(summary['protected_input_sha256_before']==summary['protected_input_sha256_final'] and all(sha256(path)==h for path,h in summary['protected_input_sha256_before'].items()),'Source hash changed'))
def retime(_):
 qa=json.loads((W/'retime-qa.json').read_text());return require(qa['input_cues']==3 and qa['output_cues']==2 and qa['removed_cues']==[2] and qa['deleted_seconds']==1.0 and '00:00:01,000 --> 00:00:04,000' in (W/'revised.srt').read_text(),'Retime QA')
s.run('retime QA',needs=[W/'retime-qa.json',W/'revised.srt'],action=retime)
cfg=O/'headframe-config.json';cfg.write_text(json.dumps({'output_dir':str(O/'headframes'),'font_file':str(a.font) if a.font else 'missing-font','jobs':[{'id':'synthetic','video':str(W/'clip.mp4'),'timestamps':[.9,2.6,4.8]}]}))
s.run('headframe extraction',[sys.executable,'-B',R/'modules/trailers/scripts/extract_headframe_candidates.py',cfg],needs=[W/'clip.mp4'],feature='trailers:full')
for label,path,time in [('multi-cjk',W/'clip.mp4',.9),('second-cue',W/'clip.mp4',2.6),('review-cjk',review,.9)]:
 s.run(label+' frame',[FF,'-v','error','-ss',time,'-i',path,'-frames:v','1',O/(label+'.png')],needs=[path],feature='locked-revision:full')
def tail(_):
 import numpy as np
 def pcm(path):return np.frombuffer(subprocess.check_output([FF,'-v','error','-i',path,'-ac','1','-ar','48000','-f','f32le','-']),dtype='<f4')
 ref=pcm(W/'reference.wav');render=pcm(W/'conformed.mp4');begin=15*48000;end=min(len(ref),len(render),16*48000);corr=float(np.corrcoef(ref[begin:end],render[begin:end])[0,1]);require(corr>=.99,'Tail correlation');return {'range_seconds':[15,16],'samples':end-begin,'correlation':corr,'original_validator_warning_preserved':True}
s.run('short tail diagnostic',needs=[W/'reference.wav',W/'conformed.mp4'],feature='video-conform:full',action=tail)
report=s.save();(O/'results.json').write_text(json.dumps({'items':s.rows,'counts':report['counts'],'ok':report['ok'],'human_full_review':'NOT RUN'},ensure_ascii=False,indent=2));print(json.dumps({'cases':len(s.rows),'counts':report['counts'],'ok':report['ok']}));raise SystemExit(0 if report['ok'] else 1)
