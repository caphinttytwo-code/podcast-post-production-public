#!/usr/bin/env python3
"""Compare 15 new CLI surfaces with pinned source snapshots, offline."""
import argparse,json,os,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package
from shared.package_identity import extract_fixtures,verify
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args();verify(ROOT);out=outside_package(a.report_dir);out.mkdir(parents=True,exist_ok=False);source=extract_fixtures(ROOT/'tests/resources/rc63-source-updates.zip',out/'sources')
 specs=[('audio-edit','audio-v1.7','review.py',x) for x in ['build','launch','serve']]+[('audio-edit','audio-v1.7','multitrack.py',x) for x in ['inspect','prepare','compile','render','review','verify']]+[('audio-edit','audio-v1.7','prepare_asr_chunks.py',None)]+[('video-conform','subtitle-pr4','subtitle_review.py',x) for x in ['scan-numbers','build','serve','apply']]+[('video-conform','subtitle-pr4','audit_subtitle_sources.py',None)]
 rows=[]
 for i,(mode,folder,name,entry) in enumerate(specs):
  options=[];runs=[]
  for label,path in [('source',source/folder/'scripts'/name),('candidate',ROOT/'modules'/mode/'scripts'/name)]:
   command=[sys.executable,'-B',str(path),*([entry] if entry else []),'--help'];r=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'});log=r.stdout+r.stderr;filename=f'{i:02}-{label}.log';(out/filename).write_text(log);options.append(set(re.findall(r'--[a-zA-Z][\w-]*',r.stdout)));runs.append({'exit_code':r.returncode,'command':command,'log':filename})
  ok=all(x['exit_code']==0 for x in runs) and options[0]==options[1]
  rows.append({'case':mode+'/'+name+':'+(entry or 'root'),'status':'PASS' if ok else 'BLOCKED' if any('ModuleNotFoundError' in (out/x['log']).read_text() for x in runs) else 'FAIL','runs':runs,'source_options':sorted(options[0]),'candidate_options':sorted(options[1])})
 report={'items':rows,'ok':all(x['status']=='PASS' for x in rows)};(out/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps({'interfaces':len(rows),'ok':report['ok']}));return 0 if report['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
