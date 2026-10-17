"""Synchronized multitrack PCM editing. No alignment repair or mastering.

All positions are integer frames on a shared clock; paths are project-relative.
Source files and existing review versions are never overwritten.
"""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory

import argparse
import copy
import csv
import html
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np
import preserve_pcm as pcm
import review

UNSUPPORTED = ('本 Skill 不支持不同长度、不同采样率或未同步的音轨；'
               '请先完成外部对齐。不会自动补齐、拉伸或修复。')


def digest(path):
    return pcm.digest(path)


def fingerprint(value):
    return hashlib.sha256(review.canonical(value)).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    review.atomic(Path(path), value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('Use stable ASCII IDs, not paths or filenames')
    return value


def integer(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer sample frame')
    return value


def project(path):
    path = Path(path).resolve()
    data = load(path)
    if data.get('version') != 1 or data.get('recording_mode') != 'synchronized-multitrack':
        raise ValueError('Expected a version 1 synchronized-multitrack project')
    identifier(data.get('id'))
    tracks = data.get('tracks')
    if not isinstance(tracks, list) or len(tracks) < 2:
        raise ValueError('At least two separate synchronized tracks are required')
    items = copy.deepcopy(tracks)
    if data.get('reference_mix'):
        items.append(copy.deepcopy(data['reference_mix']))
    ids, paths = set(), set()
    for item in items:
        key = identifier(item.get('id'))
        p = (path.parent / item['path']).resolve()
        if key in ids or p in paths or not p.is_file():
            raise ValueError('Duplicate IDs, duplicate media or missing local source')
        ids.add(key); paths.add(p)
        item['resolved_path'] = str(p)
    if not data.get('reference_mix') and 'analysis-mix' in ids:
        raise ValueError('analysis-mix is reserved for the generated listening proxy')
    return path, data, items


def read_mono(path, start, length):
    with wave.open(str(path), 'rb') as f:
        f.setpos(start)
        x = pcm.decode(f.readframes(length), f.getsampwidth(), f.getnchannels())
        if len(x) != length:
            raise ValueError('Truncated alignment anchor')
        # Choosing the strongest channel avoids cancellation in a stereo reference.
        return x[:, int(np.argmax(np.sum(x*x, axis=0)))] / (1 << (8*f.getsampwidth()-1))


def lag_evidence(x, y, max_lag):
    x, y = x-x.mean(), y-y.mean()
    norm = float(np.linalg.norm(x)*np.linalg.norm(y))
    if norm < len(x)*1e-10:
        return None
    size = 1 << (2*len(x)-1).bit_length()
    c = np.fft.irfft(np.fft.rfft(y, size)*np.conj(np.fft.rfft(x, size)), size)
    lags = np.arange(-max_lag, max_lag+1)
    values = np.abs(c[lags % size])/norm
    k = int(np.argmax(values)); peak = float(values[k])
    distant = values[np.abs(lags-lags[k]) > 2]
    ambiguous = len(distant) and float(distant.max()) >= peak*.99999
    if peak < .8 or ambiguous:
        return None
    return {'lag_frames': int(lags[k]), 'correlation': peak}


def inspect(path):
    path, data, items = project(path)
    specs = {}
    for item in items:
        p = Path(item['resolved_path'])
        spec = pcm.pcm_info(p)
        if spec['frames'] < 256:
            raise ValueError('Insufficient duration for synchronization evidence')
        h = digest(p)
        if item.get('sha256') != h:
            raise ValueError('Missing/changed bound source hash; prepare or rebind the source project first')
        if item.get('original_path') and digest(path.parent/item['original_path']) != item['original_sha256']:
            raise ValueError('Original compressed source changed')
        specs[item['id']] = {**spec, 'sha256': h}
    if len({(s['frames'], s['sample_rate']) for s in specs.values()}) != 1:
        raise ValueError(UNSUPPORTED)
    first = next(iter(specs.values())); n, rate = first['frames'], first['sample_rate']
    track_items = items[:len(data['tracks'])]
    anchors, observed = [], {x['id']: [] for x in track_items}
    attestation = data.get('clock_evidence', {})
    attested = (attestation.get('confirmed') is True and
                attestation.get('type') == 'common-sample-clock' and
                all(isinstance(attestation.get(k), str) and attestation[k].strip()
                    for k in ('session', 'sample_zero', 'reviewer')))
    if data.get('reference_mix'):
        width = min(rate*2, n//8)
        starts = sorted(set(np.linspace(0, n-width, 9).astype(int).tolist()))
        for ai, start in enumerate(starts):
            x = np.column_stack([read_mono(i['resolved_path'], start, width) for i in track_items])
            y = read_mono(items[-1]['resolved_path'], start, width)
            x -= x.mean(axis=0); y -= y.mean()
            coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
            row = {'start_frame': start, 'length_frames': width, 'tracks': {}}
            for i, track in enumerate(track_items):
                # Remove other contemporaneous stems from the reference. A delayed
                # target remains in the residual rather than being aligned by us.
                residual = y-x@coefficients+x[:, i]*coefficients[i]
                found = lag_evidence(x[:, i], residual, min(rate//20, width//8))
                row['tracks'][track['id']] = found
                if found:
                    observed[track['id']].append((ai, found['lag_frames']))
                    if found['lag_frames'] != 0:
                        raise ValueError(UNSUPPORTED + f" ({track['id']}: anchor {ai}, lag {found['lag_frames']} frames)")
            anchors.append(row)
    verified = {k: len(v) >= 3 and any(i <= 2 for i, _ in v) and
                any(3 <= i <= 5 for i, _ in v) and any(i >= 6 for i, _ in v)
                for k, v in observed.items()}
    if not all(verified.values()) and not attested:
        raise ValueError('同步证据不足：等长不等于同步；请提供独立Mix或已核实的共同采样时钟依据。' + UNSUPPORTED)
    return {'project_sha256': digest(path), 'frames': n, 'sample_rate': rate,
            'sources': specs, 'alignment': {'status': 'passed', 'anchors': anchors,
                'per_track_signal_verified': verified,
                'basis': 'independent-reference-signal' if all(verified.values()) else 'explicit-common-clock-evidence',
                'clock_evidence': attestation if attested else None},
            'signal_evidence_is_not_listening': True}


def prepared_project(source, output):
    """Decode lossy sources once at native rate; never repair count differences."""
    source, data, items = project(source)
    guard_directory(output, source, *[i["resolved_path"] for i in items])
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new preparation directory')
    outside_skill(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=output.parent) as tmp:
        root = Path(tmp); prepared = copy.deepcopy(data)
        for index, item in enumerate(items):
            src = Path(item['resolved_path']); dest = root/(item['id']+'.wav')
            original_hash=digest(src)
            if item.get('sha256',original_hash)!=original_hash:
                raise ValueError('Original source hash differs from preparation request')
            if src.suffix.lower() == '.wav':
                pcm.pcm_info(src); shutil.copy2(src, dest)
            else:
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                '-i', str(src), '-map', '0:a:0', '-vn', '-c:a', 'pcm_s24le',
                                '-n', str(dest)], check=True)
            record = {k:v for k,v in item.items() if k != 'resolved_path'}
            if digest(src)!=original_hash:raise ValueError('Original source changed during preparation')
            record.update(path=dest.name, sha256=digest(dest), original_path=str(src),
                          original_sha256=original_hash)
            if index < len(data['tracks']): prepared['tracks'][index] = record
            else: prepared['reference_mix'] = record
        write(root/'project.json', prepared)
        evidence = inspect(root/'project.json')
        write(root/'preparation-qa.json', evidence)
        # No output survives unsupported inputs; no padding/resampling options.
        os.rename(root, output)
    return output/'project.json'


def outside_skill(path):
    guard_directory(path)
    if Path(path).resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Keep project artifacts outside the reusable Skill repository')


def decisions(plan, project_path):
    if plan.get('review_directory'):
        store = review.Store(project_path.parent/plan['review_directory'])
        if store.binding.get('multitrack_project_sha256') != digest(project_path):
            raise ValueError('Review belongs to another multitrack project')
        for edit in plan.get('edits',[]):
            if store.by.get(edit['id'],{}).get('operation') != edit:
                raise ValueError('Operation changed after listening review; make a new review version')
        state=store.read()
        return ({k:{'choice':v['decision'], 'note':v['note']} for k,v in state['items'].items()},
                {'directory':str(store.root),'revision':state['revision'],'state_sha256':fingerprint(state)})
    evidence = plan.get('user_decisions', {})
    if evidence.get('authority') != 'user' or not evidence.get('recorded_at'):
        raise ValueError('Record explicit user decisions or use bound review state')
    return evidence.get('items', {}), None


def compile_plan(project_path, plan_path):
    project_path = Path(project_path).resolve(); plan_path = Path(plan_path).resolve()
    validation = inspect(project_path); plan = load(plan_path)
    if plan.get('version') != 1 or plan.get('project_sha256') != validation['project_sha256']:
        raise ValueError('Plan version/project binding mismatch')
    identifier(plan.get('id'))
    rate, total = validation['sample_rate'], validation['frames']
    chosen, review_snapshot = decisions(plan, project_path)
    base = plan.get('base_range', [0, total])
    if not isinstance(base, list) or len(base) != 2:
        raise ValueError('Invalid base range')
    a, b = [integer(x, 'base range') for x in base]
    if not 0 <= a < b <= total:
        raise ValueError('Invalid base range')
    if base != [0, total] and chosen.get(plan.get('base_range_decision_id'), {}).get('choice') not in {'adopt', 'delete'}:
        raise ValueError('Trimming the body/workspace requires its own user decision')
    fade = integer(plan.get('crossfade_frames', round(.02*rate)), 'crossfade')
    if not .015 <= fade/rate <= .030:
        raise ValueError('Use a 15–30ms local crossfade')
    removals, events, retained, pending, approved, seen = [], [], [], [], [], set()
    if plan.get('base_range_decision_id') and chosen.get(plan['base_range_decision_id'],{}).get('choice') in {'adopt','delete'}:
        approved.append(plan['base_range_decision_id'])
    for order, edit in enumerate(plan.get('edits', [])):
        key = identifier(edit.get('id'))
        if key in seen: raise ValueError('Duplicate operation ID')
        seen.add(key)
        choice = chosen.get(key, {}).get('choice', 'pending')
        if choice in {'pending', 'uncertain', 'custom'}:
            pending.append(key); continue
        kind = edit.get('type')
        if kind not in {'delete', 'insert', 'replace', 'move'}:
            raise ValueError('Unknown operation')
        if choice == 'keep':
            s, e = edit.get('start_frame'), edit.get('end_frame')
            if s is not None and e is not None:
                integer(s, 'keep start'); integer(e, 'keep end')
                if not a <= s < e <= b: raise ValueError('Invalid protected keep range')
                retained.append((s, e, key))
            continue
        if choice not in {'delete', 'adopt'} or (choice == 'delete' and kind != 'delete'):
            raise ValueError('Decision does not approve this operation')
        if kind != 'delete' and edit.get('block_mode') not in {'whole', 'fine'}:
            raise ValueError('Record whole-block or explicitly approved fine edit mode')
        if kind in {'delete', 'replace', 'move'}:
            s = integer(edit.get('start_frame'), 'remove start'); e = integer(edit.get('end_frame'), 'remove end')
            if not a <= s < e <= b: raise ValueError('Removal outside authorized base')
            removals.append((s, e, key))
        if kind != 'delete':
            s = integer(edit.get('source_start_frame'), 'source start'); e = integer(edit.get('source_end_frame'), 'source end')
            if not 0 <= s < e <= total: raise ValueError('Invalid insertion source')
            if kind == 'move' and (s, e) != (edit['start_frame'], edit['end_frame']):
                raise ValueError('Move must consume exactly its source interval')
            at = edit['start_frame'] if kind == 'replace' else integer(edit.get('at_frame'), 'destination')
            if not a <= at <= b or (kind == 'move' and s <= at < e):
                raise ValueError('Invalid move/insertion destination')
            buffer = integer(edit.get('buffer_frames', 0), 'buffer')
            if buffer < 0: raise ValueError('Negative buffer')
            parts = ([{'kind':'silence', 'frames':buffer, 'decision_id':key}] if buffer else [])
            parts += [{'kind':'source', 'source_start':s, 'source_end':e, 'decision_id':key}]
            parts += ([{'kind':'silence', 'frames':buffer, 'decision_id':key}] if buffer else [])
            events.append((at, order, parts))
        approved.append(key)
    removals.sort()
    if any(removals[i][0] < removals[i-1][1] for i in range(1, len(removals))):
        raise ValueError('Overlapping replacements/removals require one combined decision')
    for s, e, key in retained:
        if any(s < end and e > start for start, end, _ in removals):
            raise ValueError('An approved removal overrides an explicit keep decision: '+key)
    for at, _, _ in events:
        if any(s < at < e for s,e,_ in removals):
            raise ValueError('Insertion destination is inside a removed interval')
    # Partition the base timeline at approved event boundaries only.
    points = sorted({a,b} | {p for s,e,_ in removals for p in (s,e)} | {p for p,_,_ in events})
    raw = []
    for i, point in enumerate(points):
        for at, _, parts in sorted(events, key=lambda x:(x[0], x[1])):
            if at == point: raw.extend(parts)
        if i+1 < len(points) and not any(s <= point < e for s,e,_ in removals):
            raw.append({'kind':'source','source_start':point,'source_end':points[i+1], 'decision_id':'base'})
    merged = []
    for item in raw:
        if (merged and item['kind'] == merged[-1]['kind'] == 'source' and
            item['source_start'] == merged[-1]['source_end'] and
            item['decision_id'] == merged[-1]['decision_id']):
            merged[-1]['source_end'] = item['source_end']
        else: merged.append(item.copy())
    if not any(x['kind'] == 'source' for x in merged): raise ValueError('Timeline removes all audio')
    nodes, pos = [], 0
    def append(kind, length, **fields):
        nonlocal pos
        if length: nodes.append({'kind':kind,'start':pos,'end':pos+length,**fields}); pos += length
    for i, item in enumerate(merged):
        if item['kind'] == 'silence':
            append('silence', item['frames'], decision_id=item['decision_id']); continue
        start, end = item['source_start'], item['source_end']; previous = merged[i-1] if i else None
        following = merged[i+1] if i+1 < len(merged) else None
        before = bool(previous and previous['kind'] == 'source')
        after = bool(following and following['kind'] == 'source')
        fade_in = bool(not before and (previous or start != 0))
        fade_out = bool(not after and (following or end != total))
        head = fade if before or fade_in else 0; tail = fade if after or fade_out else 0
        if end-start <= head+tail: raise ValueError('Source block too short for local fades')
        if fade_in: append('fade', fade, source_start=start, direction='in', decision_id=item['decision_id'])
        append('copy', end-start-head-tail, source_start=start+head, decision_id=item['decision_id'])
        if after: append('crossfade', fade, source_a=end-fade, source_b=following['source_start'], decision_id=following['decision_id'])
        elif fade_out: append('fade', fade, source_start=end-fade, direction='out', decision_id=item['decision_id'])
    return {'version':1, 'id':plan['id'], 'recording_mode':'synchronized-multitrack',
            'project_sha256':validation['project_sha256'], 'plan_sha256':digest(plan_path),
            'sample_rate':rate, 'source_frames':total, 'output_frames':pos, 'nodes':nodes,
            'approved_ids':approved, 'pending_ids':pending, 'user_decisions':chosen,
            'review_snapshot':review_snapshot,
            'alignment':validation['alignment'], 'source_specs':validation['sources'],
            'sound_processing':'preserve_source_no_mastering', 'release_ready':False}


def node_audio(source, spec, node):
    length = node['end']-node['start']; width, channels = spec['sample_width'], spec['channels']
    def read(start):
        source.setpos(start); raw = source.readframes(length)
        if len(raw) != length*width*channels: raise ValueError('Truncated source')
        return pcm.decode(raw, width, channels)
    if node['kind'] == 'silence': return bytes(length*width*channels)
    alpha = (np.arange(1, length+1)/(length+1))[:,None]
    if node['kind'] == 'crossfade':
        x, y = read(node['source_a']), read(node['source_b'])
        return pcm.encode(x*(1-alpha)+y*alpha, width)
    return pcm.encode(read(node['source_start'])*(alpha if node['direction']=='in' else 1-alpha), width)


def write_track(source, destination, spec, nodes):
    guard_path(destination, source)
    with wave.open(str(source),'rb') as src, wave.open(str(destination),'wb') as out:
        out.setparams((spec['channels'], spec['sample_width'], spec['sample_rate'], 0, 'NONE', 'not compressed'))
        for node in nodes:
            size = node['end']-node['start']
            if node['kind'] == 'copy':
                src.setpos(node['source_start'])
                while size:
                    n = min(size, 65536); raw = src.readframes(n)
                    if len(raw) != n*spec['channels']*spec['sample_width']: raise ValueError('Truncated source')
                    out.writeframesraw(raw); size -= n
            elif node['kind'] == 'silence':
                while size:
                    n = min(size, 65536); out.writeframesraw(bytes(n*spec['channels']*spec['sample_width'])); size -= n
            else: out.writeframesraw(node_audio(src, spec, node))


def verify_track(source, destination, spec, timeline):
    actual = pcm.pcm_info(destination)
    if actual != {k:spec[k] for k in actual} | {'frames':timeline['output_frames']}:
        raise ValueError('Output format or frame count differs')
    with wave.open(str(source),'rb') as src, wave.open(str(destination),'rb') as out:
        for node in timeline['nodes']:
            size = node['end']-node['start']; out.setpos(node['start'])
            if node['kind'] == 'copy': src.setpos(node['source_start'])
            if node['kind'] in {'copy','silence'}:
                while size:
                    n = min(size, 65536); expected = src.readframes(n) if node['kind']=='copy' else bytes(n*spec['channels']*spec['sample_width'])
                    if out.readframes(n) != expected: raise ValueError('Preserved PCM or digital silence differs')
                    size -= n
            elif out.readframes(size) != node_audio(src,spec,node):
                raise ValueError('Local fade differs from bound contributors')
    if digest(source) != spec['sha256']: raise ValueError('Source changed during render')
    return {'status':'passed','sha256':digest(destination),'frames':actual['frames'],
            'source_sha256':spec['sha256'],'format':actual,'retained_pcm_byte_identical':True,
            'local_fades_reconstructed':True,'digital_silence_verified':True}


def analysis_mix(path, destination):
    guard_path(destination, path, *[i["resolved_path"] for i in project(path)[2]])
    """A labelled listening proxy, never independent synchronization evidence."""
    path, data, items = project(path); validation = inspect(path)
    destination = Path(destination)
    if destination.exists(): raise FileExistsError(destination)
    n, rate = validation['frames'], validation['sample_rate']
    with wave.open(str(destination),'wb') as out:
        out.setparams((1,3,rate,0,'NONE','not compressed'))
        for start in range(0,n,65536):
            length=min(65536,n-start)
            # Fixed average preserves headroom; it is not a mastering operation.
            x=sum(read_mono(i['resolved_path'],start,length) for i in items[:len(data['tracks'])])/len(data['tracks'])
            out.writeframesraw(pcm.encode(x[:,None]*8388607,3))
    return destination


def transcript_projection(transcript, timeline):
    if transcript.get('project_sha256') != timeline['project_sha256']:
        raise ValueError('Transcript belongs to another source project')
    spans = {}
    for node in timeline['nodes']:
        if node['kind']=='silence': continue
        for key in (['source_a','source_b'] if node['kind']=='crossfade' else ['source_start']):
            a=node[key];spans.setdefault(node['start']-a,[]).append((a,a+node['end']-node['start']))
    pieces=[]
    for delta, intervals in spans.items():
        merged=[]
        for a,b in sorted(intervals):
            if merged and a<=merged[-1][1]: merged[-1][1]=max(b,merged[-1][1])
            else: merged.append([a,b])
        pieces.extend((a,b,delta) for a,b in merged)
    rows, issues = [], []
    for si,(a,b,delta) in enumerate(sorted(pieces,key=lambda x:x[0]+x[2])):
        for r in transcript.get('sentences',[]):
            rs=integer(r['start_frame'],'sentence start'); re_=integer(r['end_frame'],'sentence end')
            if not 0<=rs<=re_<=timeline['source_frames']: raise ValueError('Invalid transcript timing')
            if rs==re_:
                if a<=rs<b: issues.append({'id':r['id'],'reason':'zero-duration event preserved as unresolved evidence'})
                continue
            if re_<=a or rs>=b: continue
            start,end,text=rs,re_,r['text']
            if rs<a or re_>b:
                if not r.get('words'): raise ValueError('Boundary crosses a sentence without word timings; do not invent a transcript cut')
                words=[]
                for w in r['words']:
                    ws=integer(w['start_frame'],'word start');we=integer(w['end_frame'],'word end')
                    if not rs<=ws<=we<=re_: raise ValueError('Invalid word timing')
                    if max(a,rs)<=(ws+we)/2<min(b,re_):words.append(w)
                if not words: continue
                text=''.join(w['text']+w.get('punctuation','') for w in words)
                start=max(a,words[0]['start_frame']);end=min(b,words[-1]['end_frame'])
                if start>=end:
                    issues.append({'id':r['id'],'reason':'retained words have no positive duration'});continue
            rows.append({'source_id':r['id'],'speaker':r.get('speaker') or '身份待核',
                         'start_frame':start+delta,'end_frame':end+delta,'text':text,'span':si})
    rows.sort(key=lambda x:(x['start_frame'],x['end_frame']))
    return {'transcript_role':'cached-source-transcript-projection','sentences':rows,'timing_issues':issues,
            'actual_output_asr':'not_run','human_word_proofreading':'not_completed'}


def clock(frame, rate):
    ms=round(frame*1000/rate)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def history_records(path, seen=None):
    seen=set() if seen is None else seen;path=Path(path).resolve()
    if path in seen or len(seen)>=100: raise ValueError('Invalid history cycle or excessive depth')
    seen.add(path);record=load(path);rows=[]
    if record.get('parent_record'):
        parent=(path.parent/record['parent_record']).resolve()
        if digest(parent)!=record['parent_record_sha256']: raise ValueError('Parent version record changed')
        rows=history_records(parent,seen)
    return rows+[record]


def join_previews(root, timeline, items, data, artifacts, project_path):
    points=sorted({n['start'] for n in timeline['nodes'] if n['kind']=='crossfade'} |
                  {p for n in timeline['nodes'] if n['kind']=='silence' for p in (n['start'],n['end'])} |
                  {0 for n in timeline['nodes'] if n['kind']=='fade' and n['start']==0})
    mix_id=data['reference_mix']['id'] if data.get('reference_mix') else 'analysis-mix'
    ready=next((a for a in artifacts if a['id']==mix_id),None)
    reference=None
    if ready:audio=root/ready['file']
    elif points:
        generated=not data.get('reference_mix')
        source=(analysis_mix(project_path,root/'temporary-analysis.wav') if generated else Path(items[-1]['resolved_path']))
        spec={**pcm.pcm_info(source),'sha256':digest(source)};audio=root/'listening-reference.wav'
        write_track(source,audio,spec,timeline['nodes']);qa=verify_track(source,audio,spec,timeline)
        reference={'file':audio.name,'generated_analysis_mix':generated,**qa}
        if generated:source.unlink()
    else:audio=None
    clips=[]
    if points:
        (root/'joins').mkdir()
        with wave.open(str(audio),'rb') as src:
            for i,point in enumerate(points,1):
                start=max(0,point-12*timeline['sample_rate']);end=min(timeline['output_frames'],point+18*timeline['sample_rate'])
                dest=root/'joins'/f'join-{i:03}.wav'
                with wave.open(str(dest),'wb') as out:
                    out.setparams((src.getnchannels(),src.getsampwidth(),src.getframerate(),0,'NONE','not compressed'))
                    src.setpos(start);remaining=end-start
                    while remaining:
                        count=min(remaining,65536);out.writeframesraw(src.readframes(count));remaining-=count
                clips.append({'file':str(dest.relative_to(root)),'output_join_frame':point,
                              'clip_start_frame':start,'clip_end_frame':end,'join_in_clip_frame':point-start,
                              'sha256':digest(dest)})
    write(root/'join-previews.json',{'clips':clips,'listening_reference':reference,'actual_join_listening':'not_run'})
    cards=[]
    for c in clips:
        cards.append(f'<article><h2>{clock(c["output_join_frame"],timeline["sample_rate"])}</h2>'
                     f'<p>试听内接点：{clock(c["join_in_clip_frame"],timeline["sample_rate"])}</p>'
                     f'<audio controls preload="none" src="{c["file"]}"></audio></article>')
    full=f'<audio controls preload="none" src="{html.escape(audio.name)}"></audio>' if audio else ''
    title=html.escape(timeline['id'])
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} 接点试听</title><style>body{{font:17px/1.8 system-ui,sans-serif;background:#f5f3ed;color:#263d36;margin:0}}main{{max-width:1000px;margin:auto;padding:24px}}header,article{{padding:22px;background:#fffefa;border:1px solid #dbe1d6;border-radius:12px;margin:16px 0}}audio{{width:100%}}</style><main><header><h1>{title} 接点试听</h1><p>技术检查通过；实际接点及全长仍待人工审听。临时审听混音不代表正式混音成品。</p>{full}<p><a href="全版本处理记录.md">版本与用户选择</a> · <a href="时间映射.csv">源时间与新版时间</a></p></header>{''.join(cards)}</main></html>'''
    (root/'接点试听.html').write_text(page,encoding='utf-8')
    return reference


def render(project_path, plan_path, output, selection='all', transcript_path=None):
    guard_directory(output, project_path, plan_path, transcript_path)
    project_path=Path(project_path).resolve();plan_path=Path(plan_path).resolve();output=Path(output).resolve()
    if output.exists(): raise FileExistsError('Never replace an existing audio/review version')
    outside_skill(output);timeline=compile_plan(project_path,plan_path)
    _, data, items=project(project_path);plan=load(plan_path);parent=None;earlier=[]
    if plan.get('parent_record'):
        parent=(plan_path.parent/plan['parent_record']).resolve()
        if digest(parent)!=plan.get('parent_record_sha256'): raise ValueError('Bind the parent record hash')
        earlier=history_records(parent)
        previous=earlier[-1]
        if previous['project_sha256']==timeline['project_sha256']:
            revised=set(plan.get('revised_ids',[]))
            previous_ops={x['id']:x for x in previous.get('operations',[])}
            current_ops={x['id']:x for x in plan.get('edits',[])}
            for key,value in previous['user_decisions'].items():
                current=timeline['user_decisions'].get(key)
                if current is None:
                    raise ValueError('A cumulative revision omitted an earlier user decision: '+key)
                changed=(current.get('choice')!=value.get('choice') or previous_ops.get(key)!=current_ops.get(key))
                if changed and key not in revised:
                    raise ValueError('Explicitly list revised_ids before changing prior decisions/operations: '+key)
            current_base=plan.get('base_range',[0,timeline['source_frames']])
            if previous.get('base_range',[0,timeline['source_frames']])!=current_base:
                key=plan.get('base_range_decision_id')
                if key not in revised or timeline['user_decisions'].get(key,{}).get('choice') not in {'adopt','delete'}:
                    raise ValueError('Changing a previous body/workspace boundary requires a revised base decision')
        else:
            previous_hashes={x['id']:x['sha256'] for x in previous['artifacts'] if x.get('source_track')}
            if any(previous_hashes.get(i['id'])!=timeline['source_specs'][i['id']]['sha256'] for i in items):
                raise ValueError('New source project does not match parent outputs')
    projected=transcript_projection(load(transcript_path),timeline) if transcript_path else None
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.render-',dir=output.parent) as temp:
        root=Path(temp);chosen=items if selection=='all' else items[:len(data['tracks'])] if selection=='tracks' else items[len(data['tracks']):]
        sources=[(i,Path(i['resolved_path']),timeline['source_specs'][i['id']]) for i in chosen]
        if selection in {'mix','all'} and not data.get('reference_mix'):
            proxy=root/'analysis-source.wav';analysis_mix(project_path,proxy);spec={**pcm.pcm_info(proxy),'sha256':digest(proxy)}
            sources.append(({'id':'analysis-mix','generated_analysis_mix':True},proxy,spec))
        artifacts=[]
        for item,source,spec in sources:
            dest=root/(item['id']+'.wav');write_track(source,dest,spec,timeline['nodes'])
            qa=verify_track(source,dest,spec,timeline)
            artifacts.append({'id':item['id'],'file':dest.name,'source_track':not item.get('generated_analysis_mix',False),
                              'generated_analysis_mix':item.get('generated_analysis_mix',False),**qa})
        if (root/'analysis-source.wav').exists():
            (root/'analysis-source.wav').unlink()  # Internal temporary proxy, not a delivery.
        write(root/'timeline.json',timeline)
        with (root/'时间映射.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(['节点','源一开始采样点','源二开始采样点','长度采样点','新版开始采样点','新版结束采样点','新版起点','新版终点','关联决定'])
            for node in timeline['nodes']:
                writer.writerow([node['kind'],node.get('source_start',node.get('source_a','')),node.get('source_b',''),
                                 node['end']-node['start'],node['start'],node['end'],clock(node['start'],timeline['sample_rate']),clock(node['end'],timeline['sample_rate']),node.get('decision_id','')])
        reference=join_previews(root,timeline,items,data,artifacts,project_path)
        record={'version':timeline['id'],'project_sha256':timeline['project_sha256'],
                'plan_sha256':timeline['plan_sha256'],'created_at':review.now(),
                'output_frames':timeline['output_frames'],'sample_rate':timeline['sample_rate'],
                'selection':selection,
                'base_range':plan.get('base_range',[0,timeline['source_frames']]),
                'user_decisions':timeline['user_decisions'],'approved_ids':timeline['approved_ids'],
                'pending_ids':timeline['pending_ids'],'operations':plan.get('edits',[]),
                'artifacts':artifacts,'technical_status':'passed','join_listening':'not_run',
                'source_output_map':timeline['nodes'],'listening_reference':reference,
                'full_human_listening':'not_run','release_ready':False}
        if parent:
            record.update(parent_record=os.path.relpath(parent,output),parent_record_sha256=digest(parent))
        write(root/'version-record.json',record)
        text=['# 全版本处理记录\n','每版的时间码只对应该版；用户保留与待定决定不会变为删除。\n']
        for r in earlier+[record]:
            text.extend([f"## {r['version']} · {clock(r['output_frames'],r['sample_rate'])}\n",
                         '|条目|用户决定|实际执行|备注|','|---|---|---|---|'])
            for key,value in r['user_decisions'].items():
                note=str(value.get('note','')).replace('|','\\|').replace('\n','<br>')
                text.append(f"|{key}|{value['choice']}|{'已执行' if key in r['approved_ids'] else '未执行，保留'}|{note}|")
            text.append('\n技术检查通过不等于人工接点或全长听审通过。\n')
            text.extend(['\n|处理|源一范围|源二范围|本版输出范围|关联决定|','|---|---|---|---|---|'])
            for node in r.get('source_output_map',[]):
                length=node['end']-node['start']
                def source_range(key):
                    return clock(node[key],r['sample_rate'])+'–'+clock(node[key]+length,r['sample_rate']) if key in node else '—'
                text.append(f"|{node['kind']}|{source_range('source_start' if 'source_start' in node else 'source_a')}|{source_range('source_b')}|{clock(node['start'],r['sample_rate'])}–{clock(node['end'],r['sample_rate'])}|{node.get('decision_id','')}|")
        (root/'全版本处理记录.md').write_text('\n'.join(text),encoding='utf-8')
        if projected:
            write(root/'transcript.json',projected)
            lines=['# 分角色逐字稿\n','由源ASR缓存按最终时间轴映射；未重新识别成片，未逐字人工校听。\n']
            for r in projected['sentences']:
                lines.append(f"**{clock(r['start_frame'],timeline['sample_rate'])}–{clock(r['end_frame'],timeline['sample_rate'])}｜{r['speaker']}**\n\n{r['text']}\n")
            (root/'分角色逐字稿.md').write_text('\n'.join(lines),encoding='utf-8')
        # Recheck source project and plan after all outputs, before atomic publication.
        if digest(project_path)!=timeline['project_sha256'] or digest(plan_path)!=timeline['plan_sha256']:
            raise ValueError('Bound project/plan changed during render')
        if timeline['review_snapshot']:
            snapshot=timeline['review_snapshot'];state=review.Store(snapshot['directory']).read()
            if fingerprint(state)!=snapshot['state_sha256']:
                raise ValueError('User review changed during render; no version was published')
        for item in items:
            if digest(item['resolved_path'])!=timeline['source_specs'][item['id']]['sha256']:
                raise ValueError('An input changed during render')
            if item.get('original_path') and digest(project_path.parent/item['original_path'])!=item['original_sha256']:
                raise ValueError('An original source changed during render')
        write(root/'delivery-manifest.json',{'files':[{'file':str(f.relative_to(root)),'sha256':digest(f)} for f in sorted(root.rglob('*')) if f.is_file()], 'release_ready':False})
        os.rename(root,output)
    return record


def build_review(project_path, spec_path, output):
    guard_directory(output, project_path, spec_path, *[i["resolved_path"] for i in project(project_path)[2]])
    """Use the existing durable review store, binding all stems and the project."""
    project_path=Path(project_path).resolve();spec_path=Path(spec_path).resolve();output=Path(output).resolve()
    validation=inspect(project_path);_,data,items=project(project_path);spec=load(spec_path)
    if output.exists():raise FileExistsError(output)
    outside_skill(output);output.parent.mkdir(parents=True,exist_ok=True)
    # The analysis proxy is deliberately outside the review directory until build.
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.review-') as temp:
        temp=Path(temp)
        if data.get('reference_mix'):audio=items[-1]['resolved_path']
        else:audio=str(analysis_mix(project_path,temp/'analysis-mix.wav'))
        spec.update(source_audio=audio,playback_audio=audio,multitrack_project=str(project_path),
                    multitrack_sample_rate=validation['sample_rate'],
                    bound_media=[{'id':i['id'],'path':i['resolved_path']} for i in items])
        if spec.get('manuscript'):spec['manuscript']=str((spec_path.parent/spec['manuscript']).resolve())
        write(temp/'spec.json',spec);review.build(temp/'spec.json',temp/'review')
        if not data.get('reference_mix'):
            shutil.move(audio,temp/'review/analysis-mix.wav')
            manifest=load(temp/'review/manifest.json')
            manifest.update(source=str(output/'analysis-mix.wav'),audio=str(output/'analysis-mix.wav'))
            write(temp/'review/manifest.json',manifest)
        os.rename(temp/'review',output)
    return output


def verify_delivery(project_path,plan_path,delivery):
    delivery=Path(delivery).resolve();expected=compile_plan(project_path,plan_path)
    if load(delivery/'timeline.json')!=expected:raise ValueError('Stored timeline differs from source plan')
    record=load(delivery/'version-record.json');_,data,items=project(project_path)
    by={i['id']:i for i in items}
    selection=record.get('selection')
    if selection not in {'all','mix','tracks'}:raise ValueError('Missing artifact selection')
    selected=items if selection=='all' else items[:len(data['tracks'])] if selection=='tracks' else items[len(data['tracks']):]
    expected_ids={i['id'] for i in selected}
    if selection in {'all','mix'} and not data.get('reference_mix'):expected_ids.add('analysis-mix')
    if len(record['artifacts'])!=len(expected_ids) or {a['id'] for a in record['artifacts']}!=expected_ids:
        raise ValueError('Missing or duplicate selected output tracks')
    for artifact in record['artifacts']:
        if artifact['file']!=artifact['id']+'.wav':raise ValueError('Invalid artifact path')
        if artifact.get('generated_analysis_mix'):
            with tempfile.TemporaryDirectory() as temp:
                source=analysis_mix(project_path,Path(temp)/'analysis.wav')
                verify_track(source,delivery/artifact['file'],{**pcm.pcm_info(source),'sha256':digest(source)},expected)
        else:
            key=artifact['id'];verify_track(by[key]['resolved_path'],delivery/artifact['file'],expected['source_specs'][key],expected)
    reference=record.get('listening_reference')
    if reference:
        if reference['file']!='listening-reference.wav':raise ValueError('Invalid listening reference path')
        if reference['generated_analysis_mix']:
            with tempfile.TemporaryDirectory() as temp:
                source=analysis_mix(project_path,Path(temp)/'analysis.wav')
                verify_track(source,delivery/reference['file'],{**pcm.pcm_info(source),'sha256':digest(source)},expected)
        else:
            item=items[-1];verify_track(item['resolved_path'],delivery/reference['file'],expected['source_specs'][item['id']],expected)
    previews=load(delivery/'join-previews.json')
    if previews['listening_reference']!=reference:raise ValueError('Listening reference binding differs')
    if previews['clips']:
        mix_id=data['reference_mix']['id'] if data.get('reference_mix') else 'analysis-mix'
        audio=(delivery/reference['file']) if reference else delivery/next(a['file'] for a in record['artifacts'] if a['id']==mix_id)
        with wave.open(str(audio),'rb') as full:
            for clip in previews['clips']:
                if not re.fullmatch(r'joins/join-\d{3,}\.wav',clip['file']):raise ValueError('Invalid clip path')
                with wave.open(str(delivery/clip['file']),'rb') as part:
                    if part.getparams()[:3]!=full.getparams()[:3] or part.getnframes()!=clip['clip_end_frame']-clip['clip_start_frame']:
                        raise ValueError('Join preview format/length differs')
                    if clip['output_join_frame']-clip['clip_start_frame']!=clip['join_in_clip_frame']:
                        raise ValueError('Join preview timing differs')
                    full.setpos(clip['clip_start_frame']);remaining=part.getnframes()
                    while remaining:
                        count=min(remaining,65536)
                        if part.readframes(count)!=full.readframes(count):raise ValueError('Join preview does not match rendered audio')
                        remaining-=count
    for r in load(delivery/'delivery-manifest.json')['files']:
        if Path(r['file']).is_absolute() or '..' in Path(r['file']).parts:raise ValueError('Invalid manifest path')
        if digest(delivery/r['file'])!=r['sha256']:raise ValueError('Delivery artifact changed')
    return {'status':'passed','verified_selection':selection,'join_preview_pcm':'passed','actual_join_listening':'not_run','release_ready':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ['inspect','prepare','compile','render','review','verify']:
        p=sub.add_parser(name);p.add_argument('project',type=Path)
        if name in ['compile','render','verify']:p.add_argument('plan',type=Path)
        if name=='review':p.add_argument('spec',type=Path)
        if name=='verify':p.add_argument('delivery',type=Path)
        if name in ['prepare','compile','render','review']:p.add_argument('output',type=Path)
        if name=='render':
            p.add_argument('--selection',choices=['mix','tracks','all'],default='all');p.add_argument('--transcript',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='inspect':result=inspect(args.project)
        elif args.command=='prepare':result={'project':str(prepared_project(args.project,args.output))}
        elif args.command=='compile':
            if args.output.exists():raise FileExistsError(args.output)
            outside_skill(args.output);result=compile_plan(args.project,args.plan);write(args.output,result)
        elif args.command=='render':result=render(args.project,args.plan,args.output,args.selection,args.transcript)
        elif args.command=='review':result={'review':str(build_review(args.project,args.spec,args.output))}
        else:result=verify_delivery(args.project,args.plan,args.delivery)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,FileExistsError,FileNotFoundError,subprocess.CalledProcessError) as e:
        parser.exit(2,str(e)+'\n')


if __name__=='__main__':main()
