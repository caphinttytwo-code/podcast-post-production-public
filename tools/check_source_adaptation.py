#!/usr/bin/env python3
"""Reproduce rc6.3 adapters from bundled sources; optionally check older Git sources."""
import argparse,hashlib,json,subprocess,tempfile,zipfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
def sha(payload):return hashlib.sha256(payload).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream-root',type=Path);a=p.parse_args();lock=json.loads((REPO/'source-lock.json').read_text());package=REPO/'skills/podcast-post-production'
 with zipfile.ZipFile(package/'tests/resources/rc63-source-updates.zip') as archive:
  for update in lock['rc63_updates']:
   folder='audio-v1.7' if update['mode']=='audio-edit' else 'subtitle-pr4'
   with tempfile.TemporaryDirectory(prefix='pp-rc63-adapter-') as tmp:
    root=Path(tmp)
    for row in update['files']:
     payload=archive.read(folder+'/'+row['source']);
     if sha(payload)!=row.get('distributed_source_sha256',row['source_sha256']):raise ValueError('Pinned distributed source mismatch')
     relative=Path(row['runtime']).relative_to('skills/podcast-post-production');dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(payload)
    patch=REPO/update['adapter']
    subprocess.run(['git','apply','--check',str(patch)],cwd=root,check=True);subprocess.run(['git','apply',str(patch)],cwd=root,check=True)
    for row in update['files']:
     actual=REPO/row['runtime'];adapted=root/Path(row['runtime']).relative_to('skills/podcast-post-production')
     if sha(actual.read_bytes())!=row['runtime_sha256'] or actual.read_bytes()!=adapted.read_bytes():raise ValueError('Runtime adapter mismatch: '+row['runtime'])
   print(update['mode']+': bundled pinned source and rc63 adapter PASS')
 for row in lock['renderer_updates']+lock.get('asr_security_updates',[]):
  if row.get('superseded_by'):continue
  if sha((REPO/row['runtime_path']).read_bytes())!=row['runtime_sha256']:raise ValueError('Retained adapter hash changed: '+row['runtime_path'])
  if not a.upstream_root:continue
  payload=subprocess.check_output(['git','-C',str(a.upstream_root/row['mode']),'show',row['commit']+':'+row['script']])
  if sha(payload)!=row['source_sha256']:raise ValueError('Older pinned source changed')
 print('Retained module/shared adapter hashes PASS')
if __name__=='__main__':main()
