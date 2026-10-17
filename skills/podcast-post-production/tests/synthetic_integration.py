#!/usr/bin/env python3
"""21 independent/dependent synthetic production steps. No real media or model calls."""
import argparse,json,math,shutil,struct,subprocess,sys,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package,sha256
from shared.test_steps import Steps
from shared.fonts import font_path,load_font
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--review-ffmpeg',default='ffmpeg');p.add_argument('--font',type=Path);a=p.parse_args()
 w=outside_package(a.work_dir).resolve()
 if w.exists():raise FileExistsError('Use a fresh synthetic work directory')
 steps=Steps(w,review_ffmpeg=a.review_ffmpeg,font=a.font)
 def save(name,data):
  path=w/name;path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return path
 def tool(mode,name,*args):return [sys.executable,'-B',ROOT/'modules'/mode/'scripts'/name,*args]
 def ff(*args):return ['ffmpeg','-v','error','-y',*args]
 def wav(path,samples):
  with wave.open(str(path),'wb') as o:o.setnchannels(1);o.setsampwidth(2);o.setframerate(48000);o.writeframes(samples)
 # Standard-library fixture creation remains possible when optional packages are absent.
 import random
 rng=random.Random(20261008);freq=[rng.uniform(140,850) for _ in range(120)];phase=0.;raw=bytearray()
 for i in range(24*48000):
  t=i/48000;phase+=2*math.pi*freq[min(int(t*5),119)]/48000
  x=.24*(math.sin(phase)+.35*math.sin(phase*2.17))*(.65+.35*math.sin(t*1.9)**2)
  raw.extend(struct.pack('<h',int(max(-1,min(1,x))*26000)))
 source=w/'source.wav';reference=w/'reference.wav';wav(source,raw);wav(reference,raw[:8*48000*2]+raw[12*48000*2:20*48000*2]);steps.protect(source,reference)
 video=w/'source.mp4'
 steps.run('source-video',ff('-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=24','-i',source,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-shortest',video),feature='locked-revision:full',needs=[source]);steps.protect(video)
 edl=save('audio-edl.json',{'schema_version':1,'branch':'rigorous-explainer','delivery_formats':['wav'],'cuts':[{'start':8,'end':12}],'fixture_notice':'synthetic technical test, not human editorial authorization'})
 mastered=w/'mastered.wav'
 steps.run('audio-render',tool('audio-edit','render_podcast_edl.py',source,edl,mastered),feature='audio-edit:basic',needs=[source,edl])
 steps.run('audio-qa',tool('audio-edit','audio_qa.py',mastered,'--json-out',w/'audio-qa.json'),feature='audio-edit:basic',needs=[mastered],after=['audio-render'])
 project=w/'conform';manifest=project/'manifests/synthetic.json'
 steps.run('acoustic-edl',tool('video-conform','build_acoustic_edl.py','--source-video',video,'--reference-audio',reference,'--project-root',project,'--job-id','synthetic'),feature='video-conform:full',needs=[video,reference],after=['source-video'])
 steps.run('conform-sample',tool('video-conform','make_approval_sample.py',manifest,'--output-dir',w/'sample'),feature='video-conform:full',needs=[manifest],after=['acoustic-edl'])
 conformed=w/'conformed.mp4'
 steps.run('conform-render',tool('video-conform','render_reference_conform.py',manifest,'--output',conformed,'--preset','ultrafast','--execute'),feature='video-conform:full',needs=[manifest],after=['acoustic-edl'])
 def conform_qa(result):
  save('conform-qa.json',json.loads(result.stdout))
  data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(conformed)]))
  assert abs(float(data['format']['duration'])-16)<.08,'Conform duration drift'
 steps.run('conform-qa',tool('video-conform','validate_edl.py',manifest,'--output',conformed,'--content-check','--full-decode'),feature='video-conform:full',needs=[manifest,conformed],after=['conform-render'],action=conform_qa)
 srt=w/'clip.srt';srt.write_text('1\n00:00:00,000 --> 00:00:02,000\n合成测试\n多行字幕\n\n2\n00:00:02,000 --> 00:00:05,000\n技术验收\n',encoding='utf-8')
 chosen=None;family=None
 try:chosen=font_path(a.font);family=load_font(chosen,20).getname()[0]
 except (OSError,ValueError,ImportError):chosen=None;family=None
 clip=w/'clip.mp4'
 batch=save('batch.json',{'defaults':{'preset':'ultrafast'},'jobs':[{'id':'synthetic','source':str(video),'output':str(clip),'width':320,'height':480,'video_height':180,'video_y':150,'fps':30,'clips':[{'in':0,'out':3},{'in':4,'out':7}],'transition':.1,'subtitles':{'path':str(srt),'font_size':20,'font':str(chosen) if chosen else 'missing-font'}}]})
 steps.run('trailer-render',tool('trailers','render_batch.py',batch),feature='trailers:full',needs=[video,batch,srt],after=['source-video'])
 steps.run('trailer-qa',tool('trailers','qa_outputs.py',batch),feature='trailers:full',needs=[clip,batch],after=['trailer-render'])
 steps.run('trailer-decode',ff('-i',clip,'-f','null','-'),feature='trailers:full',needs=[clip],after=['trailer-render'])
 photo=w/'synthetic-photo.png'
 if chosen:
  from PIL import Image
  Image.new('RGB',(320,240),'#678c9b').save(photo)
 visual=save('visual.json',{'output_dir':str(w/'visual'),'title':[],'partnership_label':'','separator':False,'photo':{'path':str(photo),'box':[0,656,1080,608],'fade_top':0,'fade_bottom':0}})
 def visual_qa(result):
  from PIL import Image
  for filename,size in [('frame-preview.png',(1080,1920)),('frame-mobile.png',(270,480)),('frame-overlay.png',(1080,1920))]:
   with Image.open(w/'visual'/filename) as im:assert im.size==size,'Visual dimensions'
 steps.run('static-visuals',tool('trailers','build_visuals.py',visual),feature='trailers:images',needs=[photo,visual],action=visual_qa)
 review=save('review.json',{'root':str(w),'output_dir':str(w/'review'),'items':[{'video':str(clip),'srt':str(srt)}],'width':320,'height':480,'ffmpeg':a.review_ffmpeg,'timecode_font_file':str(chosen) if chosen else 'missing-font','subtitle_font_dir':str(chosen.parent) if chosen else 'missing-font','subtitle_font_name':family or 'missing-font'})
 steps.run('review-encode',tool('trailers','render_review_proxies.py',review),feature='trailers:review',needs=[clip,srt,review],after=['trailer-render'])
 parent=w/'parent-3tracks.mp4';revised=w/'revised-3tracks.mp4'
 steps.run('three-track-parent',ff('-i',video,'-f','lavfi','-i','sine=frequency=220:sample_rate=48000:duration=5','-f','lavfi','-i','sine=frequency=330:sample_rate=48000:duration=5','-t','5','-map','0:v','-map','0:a','-map','1:a','-map','2:a','-c:v','copy','-c:a','aac','-disposition:a:0','default','-disposition:a:1','0','-disposition:a:2','0',parent),feature='locked-revision:full',needs=[video],after=['source-video']);steps.protect(parent)
 graph='[0:v]split=2[v0][v1];[v0]trim=0:1,setpts=PTS-STARTPTS[x0];[v1]trim=2:5,setpts=PTS-STARTPTS[x1];[x0][x1]concat=n=2:v=1:a=0[v]'
 for i in range(3):graph+=f';[0:a:{i}]asplit=2[a{i}0][a{i}1];[a{i}0]atrim=0:1,asetpts=PTS-STARTPTS,afade=t=out:st=0.985:d=0.015[b{i}0];[a{i}1]atrim=2:5,asetpts=PTS-STARTPTS,afade=t=in:d=0.015[b{i}1];[b{i}0][b{i}1]concat=n=2:v=0:a=1[a{i}]'
 steps.run('three-track-revision',ff('-i',parent,'-filter_complex',graph,'-map','[v]','-map','[a0]','-map','[a1]','-map','[a2]','-c:v','libx264','-preset','ultrafast','-c:a','aac','-ar','48000','-disposition:a:0','default','-disposition:a:1','0','-disposition:a:2','0',revised),feature='locked-revision:full',needs=[parent],after=['three-track-parent'])
 ps=w/'parent.srt';ps.write_text('1\n00:00:00,000 --> 00:00:01,000\n保留\n\n2\n00:00:01,000 --> 00:00:02,000\n删除\n\n3\n00:00:02,000 --> 00:00:05,000\n保留\n',encoding='utf-8')
 edits=save('edits.json',{'deletions':[{'start':1,'end':2,'reason':'synthetic fixture'}]});osrt=w/'revised.srt'
 steps.run('locked-subtitles',tool('locked-revision','retime_srt.py','--input',ps,'--edits',edits,'--output',osrt,'--report',w/'retime-qa.json'),feature='locked-revision:subtitles',needs=[ps,edits])
 revision=save('revision.json',{'schema_version':1,'id':'synthetic','source':str(parent),'source_sha256':sha256(parent) if parent.exists() else None,'output':str(revised),'output_subtitle':str(osrt),'deletions':[{'start':1,'end':2}],'locked':{'geometry':True,'frame_rate':True,'audio_layout':True}})
 steps.run('locked-qa',tool('locked-revision','validate_locked_revision.py',revision,'--report',w/'locked-qa.json'),feature='locked-revision:full',needs=[parent,revised,osrt],after=['three-track-revision','locked-subtitles'])
 steps.run('locked-decode',ff('-i',revised,'-map','0','-f','null','-'),feature='locked-revision:full',needs=[revised],after=['three-track-revision'])
 for name in ['source','backup']:
  folder=w/('audit-fixture' if name=='source' else 'backup-fixture');folder.mkdir()
  shutil.copy2(source,folder/'retain.wav');shutil.copy2(reference,folder/'process.wav');steps.protect(*folder.iterdir())
  cfg=save(name+'-inventory.json',{'roots':[{'id':'fixture','path':str(folder)}],'output_dir':str(w/(name+'-audit')),'rules':{'retain':['retain.wav'],'quarantine':['process.wav']},'hash_mode':'all'})
  steps.run(name+'-inventory',tool('project-audit','inventory_project.py',cfg),feature='project-audit:inventory',needs=[cfg])
 steps.run('backup-check',tool('project-audit','verify_backups.py',w/'source-audit/inventory.json',w/'backup-audit/inventory.json','--report',w/'backup-qa.json'),feature='project-audit:inventory',needs=[w/'source-audit/inventory.json',w/'backup-audit/inventory.json'],after=['source-inventory','backup-inventory'])
 spec=save('index-spec.json',{'workflow':'video-conform','module_version':'0.2.0-rc.6.3-beta','inputs':[{'role':'source_video','path':str(video)},{'role':'reference_audio','path':str(reference)}],'artifacts':[{'role':'conformed_master','path':str(conformed),'timebase':'final'}],'review_refs':[]})
 steps.run('project-index',[sys.executable,'-B',ROOT/'scripts/project_index.py','--spec',spec,'--output',w/'project-index.json'],needs=[video,reference,conformed],after=['conform-render'])
 report=steps.save();print(json.dumps({'ok':report['ok'],'steps':len(steps.rows),'counts':report['counts'],'cloud_calls':0}));return 0 if report['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
