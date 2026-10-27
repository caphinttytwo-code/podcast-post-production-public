#!/usr/bin/env python3
"""Run the original 103 cases against current implementations; counted as reused cases."""
import importlib.util
import argparse,json,os,re,shutil,subprocess,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package
from shared.package_identity import verify,extract_fixtures,inventory,tree_digest
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args();verify(ROOT)
 out=outside_package(a.report_dir);out.mkdir(parents=True,exist_ok=False)
 fixture=out/'current-implementation-with-original-tests';shutil.copytree(ROOT,fixture)
 for directory in [fixture/'tests',*[(fixture/'modules'/x/'tests') for x in ['audio-edit','video-conform','trailers','locked-revision','project-audit']]]:
  for f in directory.glob('test_*.py'):f.unlink()
 with zipfile.ZipFile(ROOT/'tests/resources/rc62-regression-tests.zip') as z:z.extractall(fixture)
 # This is explicitly a compatibility fixture, with the current code and original tests.
 # Bind its changed test inventory instead of misrepresenting it as the frozen distribution.
 metadata=json.loads((fixture/'package-manifest.json').read_text());metadata['parent_candidate_identity']=verify(ROOT);metadata['fixture_purpose']='current implementation / rc62 original regression tests';metadata['files']=inventory(fixture);metadata['tree_sha256']=tree_digest(metadata['files']);(fixture/'package-manifest.json').write_text(json.dumps(metadata,indent=2))
 frozen=extract_fixtures(ROOT/'tests/resources/frozen-sources.zip',out/'frozen')/'sources'
 rows=[]
 for name,folder in [(n,fixture/'modules'/n/'tests') for n in ['audio-edit','video-conform','trailers','locked-revision','project-audit']]+[('shared',fixture/'tests')]:
  required={'audio-edit':['numpy'],'trailers':['PIL'],'shared':['numpy','PIL']}.get(name,[]);missing=[x for x in required if importlib.util.find_spec(x) is None]
  if missing:rows.append({'suite':name,'tests':0,'status':'BLOCKED','missing':missing,'exit_code':None});continue
  cmd=[sys.executable,'-B','-m','unittest','discover','-s',str(folder),'-v'];r=subprocess.run(cmd,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PP_FROZEN_SOURCES':str(frozen)})
  log=r.stdout+r.stderr;(out/(name+'.log')).write_text(log);count=re.search(r'Ran (\d+) tests?',log)
  rows.append({'suite':name,'tests':int(count[1]) if count else 0,'exit_code':r.returncode,'status':'PASS' if r.returncode==0 and not re.search(r'OK\s*\(skipped=',log) else 'FAIL','command':cmd,'log':name+'.log'})
 report={'suites':rows,'tests':sum(x['tests'] for x in rows),'counting':'compatibility reruns; overlap with migrated source suites, do not add as unique cases','ok':all(x['status']=='PASS' for x in rows)}
 (out/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));return 0 if report['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
