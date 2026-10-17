"""Create resumable MP3 proxies with an exact source-sample manifest, without ASR."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory

import argparse
import re
import json
import subprocess
import wave
from pathlib import Path
from transcribe_stepfun import atomic_json, sha256


def prepare(source, output, seconds=300):
    guard_directory(output, source)
    source, output=Path(source).resolve(),Path(output).resolve()
    if seconds<=0:raise ValueError('Chunk duration must be positive')
    if output.is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError('Keep project media outside Skill')
    with wave.open(str(source),'rb') as f:rate,total=f.getframerate(),f.getnframes()
    chunk_frames=round(seconds*rate)
    if chunk_frames<1 or total<1:raise ValueError('Empty source or zero-frame chunks')
    binding={'source_sha256':sha256(source),'source_frames':total,'sample_rate':rate,
             'chunk_frames':chunk_frames,'proxy_format':'mp3','proxy_sample_rate':16000,
             'proxy_channels':1,'proxy_bitrate_kbps':64}
    manifest=output/'manifest.json'
    if manifest.exists():
        state=json.loads(manifest.read_text())
        if any(state.get(k)!=v for k,v in binding.items()):raise ValueError('Existing proxy source or parameters differ')
    else:
        if output.exists() and any(output.iterdir()):raise ValueError('Unbound proxy directory; preserve and use a new path')
        output.mkdir(parents=True,exist_ok=True)
        state={**binding,'chunks':[{'name':f'chunk-{i:03}.mp3','start_frame':s,'frames':min(chunk_frames,total-s),'sha256':None}
                                  for i,s in enumerate(range(0,total,chunk_frames))]}
        atomic_json(manifest,state)
    for row in state['chunks']:
        name=Path(row['name'])
        if name.name != row['name'] or not re.fullmatch(r'chunk-[0-9]+\.mp3', row['name']): raise ValueError('Invalid proxy chunk filename')
        target=guard_path(output/row['name'], source)
        if row['sha256']:
            if not target.exists() or sha256(target)!=row['sha256']:raise ValueError('Completed proxy changed')
            continue
        temporary=target.with_suffix('.partial.mp3')
        subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{row["start_frame"]/rate:.12f}','-i',str(source),
                        '-t',f'{row["frames"]/rate:.12f}','-ar','16000','-ac','1','-c:a','libmp3lame',
                        '-b:a','64k',str(temporary)],check=True)
        temporary.replace(target);row['sha256']=sha256(target);atomic_json(manifest,state)
    return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--seconds',type=float,default=300);a=p.parse_args()
    print(json.dumps(prepare(a.source,a.output,a.seconds),ensure_ascii=False,indent=2))
