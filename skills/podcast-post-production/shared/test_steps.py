"""Dependency-aware offline test execution, with evidence even after failure."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
from .files import sha256
from . import environment


class Steps:
    def __init__(self, directory, ffmpeg='ffmpeg', ffprobe='ffprobe', review_ffmpeg=None, font=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        (self.directory/'logs').mkdir(exist_ok=True)
        self.rows=[];self.by={};self.protected={};self.gates={};self.protection_failed=False
        self.ffmpeg=ffmpeg;self.ffprobe=ffprobe;self.review_ffmpeg=review_ffmpeg or ffmpeg;self.font=font

    def protect(self,*paths):
        for path in paths:
            if Path(path).is_file():self.protected.setdefault(str(Path(path).resolve()),sha256(path))
        self.save()

    def gate(self, feature):
        if not feature:return None
        if feature not in self.gates:
            mode,part=feature.split(':',1)
            self.gates[feature]=environment.inspect(mode, feature=part,
                ffmpeg=self.review_ffmpeg if part=='review' else self.ffmpeg,
                ffprobe=self.ffprobe, font=self.font if part in ('review','images','full') and mode=='trailers' else None)
        return self.gates[feature]

    def run(self,name,command=None,*,feature=None,needs=(),after=(),action=None):
        row={'step':name,'case':name,'command':[str(x) for x in command] if command else [],'feature':feature,'needs':[str(x) for x in needs],'after':list(after),'exit_code':None}
        missing=[str(x) for x in needs if not Path(x).exists()]
        upstream=[x for x in after if self.by.get(x,{}).get('status')!='PASS']
        gate=self.gate(feature)
        if self.protection_failed:
            row.update(status='NOT RUN',reason='Stopped this batch: protected input changed')
        elif gate and not gate['ok']:
            row.update(status='BLOCKED',reason='; '.join(gate['missing']))
        elif missing or upstream:
            row.update(status='NOT RUN',reason='Upstream input unavailable or unverified',missing_inputs=missing,upstream=upstream)
        else:
            try:
                result=None
                if command:
                    result=subprocess.run([str(x) for x in command],capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'})
                    log='logs/'+name+'.txt';(self.directory/log).write_text(result.stdout+result.stderr,encoding='utf-8')
                    row.update(exit_code=result.returncode,log=log)
                    if result.returncode:
                        if 'WinError 1314' in result.stderr:row['status']='BLOCKED';row['reason']='Windows symlink permission';raise PermissionError(row['reason'])
                        raise RuntimeError(result.stderr[-1500:] or result.stdout[-1500:])
                if action:row['detail']=action(result)
                row['status']='PASS'
            except Exception as exc:
                row.setdefault('status','FAIL');row['reason']=str(exc)
        changed=[p for p,h in self.protected.items() if not Path(p).is_file() or sha256(p)!=h]
        if changed and not self.protection_failed:
            self.protection_failed=True;row.update(status='FAIL',reason='Protected input changed',protection_failure=True,changed_inputs=changed)
        self.rows.append(row);self.by[name]=row;self.save()
        return row

    def save(self):
        after={p:sha256(p) if Path(p).is_file() else None for p in self.protected}
        report={'steps':self.rows,'counts':dict(Counter(x['status'] for x in self.rows)),
          'protected_input_sha256_before':self.protected,'protected_input_sha256_after':after,
          'protected_input_sha256_final':after,'protected_inputs_unchanged':after==self.protected,
          'resource_gates':self.gates,'ok':bool(self.rows) and all(x['status']=='PASS' for x in self.rows) and after==self.protected,
          'protection_failure':self.protection_failed,'synthetic_only':True,'cloud_calls':0,'paid_calls':0,'human_review':'NOT RUN','release_ready':False}
        (self.directory/'integration-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return report


class ControlFailed(RuntimeError):
    """A rejection test is invalid unless its normal control fully succeeds."""


def protection_result(case,status,**details):
    details.pop('case',None)
    if 'control' in case.lower() and status!='PASS':
        raise ControlFailed('Normal control assertions failed: '+case+'; '+str(details))
    return {'case':case,'status':status,**details}
