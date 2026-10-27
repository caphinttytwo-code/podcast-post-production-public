"""Sample-exact integer PCM assembly. No mastering, resampling or lossy codec."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory

import hashlib
import json
import os
import tempfile
import wave
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def pcm_info(path):
    try:
        with wave.open(str(path), 'rb') as f:
            spec = dict(sample_rate=f.getframerate(), channels=f.getnchannels(),
                        sample_width=f.getsampwidth(), frames=f.getnframes())
            if f.getcomptype() != 'NONE': raise ValueError('Compressed WAV is unsupported')
    except (wave.Error, EOFError) as e:
        raise ValueError('Preserve mode requires integer PCM WAV') from e
    if spec['channels'] not in (1, 2) or spec['sample_width'] not in (2, 3, 4):
        raise ValueError('Preserve mode supports mono/stereo 16/24/32-bit integer PCM WAV')
    return spec


def decode(raw, width, channels):
    import numpy as np
    if width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        u = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        x = np.where(u >= 8388608, u - 16777216, u)
    else: x = np.frombuffer(raw, dtype='<i2' if width == 2 else '<i4')
    return x.reshape(-1, channels).astype(np.float64)


def encode(x, width):
    import numpy as np
    y = np.rint(x).astype(np.int64).reshape(-1)
    limit = 1 << (width * 8 - 1)
    if np.any(y < -limit) or np.any(y >= limit): raise ValueError('PCM overflow')
    if width != 3: return y.astype('<i2' if width == 2 else '<i4').tobytes()
    u = (y & 0xffffff).astype(np.uint32)
    b = np.empty((len(u), 3), dtype=np.uint8)
    b[:, 0] = u & 255; b[:, 1] = u >> 8 & 255; b[:, 2] = u >> 16 & 255
    return b.tobytes()


def layout(spec, cuts, fade_seconds):
    rate, total = spec['sample_rate'], spec['frames']
    fade = round(fade_seconds * rate)
    if not .015 <= fade_seconds <= .030: raise ValueError('Crossfade must be 15–30 ms')
    merged = []
    for c in sorted(cuts, key=lambda c: c['start']):
        s, e = round(float(c['start']) * rate), round(float(c['end']) * rate)
        if s < 0 or e <= s or e > total: raise ValueError('Invalid PCM cut interval')
        # Never consume an unapproved positive gap between cuts.
        if merged and s <= merged[-1][1]: merged[-1][1] = max(e, merged[-1][1])
        else: merged.append([s, e])
    keep, cursor = [], 0
    for s, e in merged:
        if s > cursor: keep.append([cursor, s])
        cursor = e
    if cursor < total: keep.append([cursor, total])
    if not keep or min(e-s for s,e in keep) <= 2*fade:
        raise ValueError('Retained segment too short for crossfade; refine the approved boundaries')
    return keep, fade


def assemble(source, output, edl, dry_run=False):
    import numpy as np
    guard_path(output, source)
    guard_path(Path(output).with_suffix(Path(output).suffix+".assembly.json"), source)
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve(): raise ValueError('Never overwrite source')
    if output.suffix.lower() != '.wav': raise ValueError('Preserve mode only delivers PCM WAV')
    spec = pcm_info(source)
    for field, value in [('sample_rate',spec['sample_rate']),('channels',spec['channels']),('wav_bit_depth',spec['sample_width']*8)]:
        if field in edl and int(edl[field]) != value: raise ValueError(f'Preserve mode cannot change {field}')
    if edl.get('pre_gain_db',0) != 0 or edl.get('highpass_hz',0) != 0:
        raise ValueError('Preserve mode prohibits gain and highpass processing')
    source_hash = digest(source)
    if edl.get('source_sha256',source_hash) != source_hash: raise ValueError('Source hash changed')
    keep, fade = layout(spec, edl.get('cuts',[]), float(edl.get('crossfade_seconds',.02)))
    expected = sum(e-s for s,e in keep) - fade*(len(keep)-1)
    report = {'profile':'preserve_source_no_mastering','source_sha256':source_hash,
              'source_spec':spec,'crossfade_frames':fade,'expected_frames':expected,
              'expected_output_seconds':expected/spec['sample_rate'], 'keep_segments':keep,
              'delivery_state':'review','auditory_review':'not_run','release_ready':False}
    if dry_run: return report
    report_path = output.with_suffix(output.suffix+'.assembly.json')
    if output.exists() or report_path.exists(): raise FileExistsError('Version output and assembly report')
    output.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=output.name+'.',suffix='.partial',dir=output.parent); os.close(fd)
    spans, joins, cursor, tail = [], [], 0, None
    width, channels, rate = spec['sample_width'], spec['channels'], spec['sample_rate']
    try:
        with wave.open(str(source),'rb') as src, wave.open(tmp,'wb') as out:
            out.setnchannels(channels); out.setsampwidth(width); out.setframerate(rate)
            for i,(s,e) in enumerate(keep):
                src.setpos(s)
                if tail is not None:
                    head=src.readframes(fade); alpha=(np.arange(1,fade+1)/(fade+1))[:,None]
                    mixed=encode(decode(tail,width,channels)*(1-alpha)+decode(head,width,channels)*alpha,width)
                    out.writeframesraw(mixed)
                    joins.append({'output_start_frame':cursor,'output_end_frame':cursor+fade,
                                  'left_source_frames':[keep[i-1][1]-fade,keep[i-1][1]],
                                  'right_source_frames':[s,s+fade],'auditory_review':'not_run',
                                  'pcm_sha256':hashlib.sha256(mixed).hexdigest()})
                    cursor+=fade; body_start=s+fade
                else: body_start=s
                body_end=e-fade if i<len(keep)-1 else e
                spans.append({'source_start_frame':body_start,'source_end_frame':body_end,
                              'output_start_frame':cursor,'output_end_frame':cursor+body_end-body_start})
                remain=body_end-body_start
                while remain:
                    n=min(rate*10,remain); b=src.readframes(n)
                    if len(b)!=n*width*channels: raise ValueError('Truncated PCM source')
                    out.writeframesraw(b); cursor+=n; remain-=n
                tail=src.readframes(fade) if i<len(keep)-1 else None
        if cursor!=expected: raise ValueError('Assembly frame count mismatch')
        report.update(unchanged_spans=spans,joins=joins,output_sha256=digest(tmp))
        result=verify(source,tmp,report)
        if not all(result.values()): raise ValueError('PCM verification failed')
        os.replace(tmp,output)
        report.update(verification=result,actual_frames=cursor)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        return report
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def verify(source, output, report):
    """Verify every body and fade sample against immutable source, not report assertions."""
    import numpy as np
    spec=pcm_info(source); actual=pcm_info(output)
    valid={'source_hash':digest(source)==report['source_sha256'],
           'output_hash':digest(output)==report.get('output_sha256'),
           'same_format':all(spec[k]==actual[k] for k in ('sample_rate','channels','sample_width')),
           'frame_count':actual['frames']==report['expected_frames']}
    # Reconstruct the complete layout from source intervals, including body coverage.
    keep=report['keep_segments'];fade=report['crossfade_frames']; width=spec['sample_width'];channels=spec['channels']
    spans,joins,cursor=[],[],0
    for i,(s,e) in enumerate(keep):
        if not (0<=s<e<=spec['frames']) or (i and s<keep[i-1][1]):raise ValueError('Invalid assembly map')
        if i:
            joins.append((cursor,keep[i-1][1]-fade,s));cursor+=fade
        bs=s+(fade if i else 0);be=e-(fade if i<len(keep)-1 else 0)
        if be<=bs:raise ValueError('Invalid retained body')
        spans.append((bs,be,cursor));cursor+=be-bs
    valid['map_covers_output']=cursor==actual['frames']
    with wave.open(str(source),'rb') as src,wave.open(str(output),'rb') as out:
        equal=True
        for s,e,t in spans:
            src.setpos(s);out.setpos(t);left=e-s
            while left:
                n=min(spec['sample_rate']*10,left)
                equal &= src.readframes(n)==out.readframes(n);left-=n
        valid['retained_samples_equal']=bool(equal)
        fades=True
        for t,left,right in joins:
            src.setpos(left);a=src.readframes(fade);src.setpos(right);b=src.readframes(fade)
            alpha=(np.arange(1,fade+1)/(fade+1))[:,None]
            expected=encode(decode(a,width,channels)*(1-alpha)+decode(b,width,channels)*alpha,width)
            out.setpos(t);fades &= out.readframes(fade)==expected
        valid['crossfades_match_source']=bool(fades)
    return valid
