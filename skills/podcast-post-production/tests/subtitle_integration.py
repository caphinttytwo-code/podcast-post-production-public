#!/usr/bin/env python3
"""Synthetic contextual review E2E. Saved decisions are simulated, never human listening."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'modules/video-conform/scripts'))
import subtitle_review as r
from shared.files import outside_package
BASE='1\n00:00:00,100 --> 00:00:02,000\n墨池深1点8米\n\n2\n00:00:02,100 --> 00:00:03,900\n只有一号馆\n\n3\n00:00:04,000 --> 00:00:05,500\n当时是2010年代\n'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args()
    work=outside_package(a.work_dir);work.mkdir(parents=True,exist_ok=False)
    steps=[]
    def check(name,ok,detail=None):
        steps.append({'case':name,'status':'PASS' if ok else 'FAIL','detail':detail})
        if not ok:raise AssertionError(name)
    source=work/'source.srt';source.write_text(BASE,encoding='utf-8');audio=work/'tone.wav'
    cmd=['ffmpeg','-v','error','-n','-f','lavfi','-i','sine=frequency=440:duration=6',str(audio)]
    result=subprocess.run(cmd,capture_output=True);(work/'tone-generation.log').write_bytes(result.stdout+result.stderr)
    check('synthetic audio',result.returncode==0,{'command':cmd,'exit_code':result.returncode})
    before={str(x):r.sha(x) for x in [source,audio]}
    items=r.scan_numbers(source,['一号馆']);r.write_json(work/'numeric-scan.json',items)
    check('numeric scan protects fixed name',[x['cue_numbers'] for x in items]==[[1],[3]])
    rows=[{'id':'depth','cue_numbers':[1],'priority':True},{'id':'name','cue_numbers':[2]},{'id':'year','cue_numbers':[3]}]
    review=work/'review';manifest=r.build_review(source,rows,review,audio=audio,profile='compact-clean',context_seconds=.5,protected_terms=['一号馆'])
    check('context clips',len(manifest['items'])==3 and manifest['items'][0]['context_after']==['只有一号馆','当时是2010年代'])
    for item in manifest['items']:
        clip=review/item['audio'];cmd=['ffmpeg','-v','error','-i',str(clip),'-f','null','-']
        result=subprocess.run(cmd,capture_output=True);(work/(item['id']+'-decode.log')).write_bytes(result.stdout+result.stderr)
        check(item['id']+' full clip decode',result.returncode==0 and r.sha(clip)==item['audio_sha256'],{'command':cmd,'exit_code':result.returncode,'sha256':r.sha(clip)})
    server=r.make_server(review);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base+'/') as response:page=response.read()
        (work/'review-page.html').write_bytes(page)
        check('local review page',all(x.encode() in page for x in ['拿不准','前文','后文','保存']))
        with urllib.request.urlopen(base+'/api/state') as response:state=json.load(response)['state']
        state['items'][0].update(decision='edit',corrected_text='墨池深1.9米',action_source='individual',note='模拟决定 非人工审听')
        request=urllib.request.Request(base+'/api/save',data=json.dumps(state).encode(),headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(request) as response:saved=json.load(response)
        state=r.load(review/'decisions.json')
        check('partial save',saved['revision']==1 and state['items'][1]['decision'] is None and state['items'][2]['decision'] is None)
        out=work/'v02.srt';qa=r.apply_review(review,out)
        old=r.read_cues(source);new=r.read_cues(out)
        check('decimal edit preserves times',new[0].lines==('墨池深1点9米',) and [(x.start,x.end) for x in old]==[(x.start,x.end) for x in new])
        check('unselected remains untouched',old[1:]==new[1:] and qa['decision_counts']=={'edit':1,'unselected':2})
        check('snapshot and no human claim',r.load(out.with_suffix('.review')/'submitted-decisions.json')==state and not qa['all_items_human_confirmed'] and not qa['human_full_audio_review'])
        state['items'][0].update(corrected_text='第一句\n\n第二句')
        state['items'][1].update(decision='uncertain',action_source='individual',note='模拟拿不准')
        request=urllib.request.Request(base+'/api/save',data=json.dumps(state).encode(),headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(request) as response:json.load(response)
        draft=work/'v03-draft.srt';qa2=r.apply_review(review,draft)
        check('no invented retiming',r.read_cues(draft)==old and len(qa2['pending'])==2 and qa2['status']=='review_draft')
    finally:server.shutdown();server.server_close();thread.join()
    after={path:r.sha(path) for path in before};check('source hashes preserved',before==after)
    r.write_json(work/'results.json',{'ok':True,'items':steps,'protected_before':before,'protected_after':after,'saved_decisions':'simulated','cloud_calls':0,'human_full_review':'NOT RUN'})
    print(json.dumps({'ok':True,'checks':len(steps),'human_full_review':'NOT RUN'}))
if __name__=='__main__':main()
