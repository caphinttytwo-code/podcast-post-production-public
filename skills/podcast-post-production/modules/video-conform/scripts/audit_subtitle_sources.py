#!/usr/bin/env python3
"""Audit explicit cue/omission lineage without making semantic or timing guesses."""
import sys
from pathlib import Path as _PPPath
sys.path.insert(0,str(_PPPath(__file__).resolve().parents[3]))
from shared.guards import guard_path
import argparse
import hashlib
import json
import math
from pathlib import Path

from validate_srt import parse_srt, validate_srt


def audit_sources(srt_text, source_map):
    if source_map.get('srt_sha256') != hashlib.sha256(srt_text.encode('utf-8')).hexdigest():
        raise ValueError('source map belongs to another SRT snapshot')
    cues, errors = parse_srt(srt_text)
    errors += validate_srt(srt_text, media_duration=max([c.end for c in cues]+[1]), max_chars=10**9, enforce_house_style=False)['errors']
    records = {}
    for record in source_map['records']:
        ident = record['id']
        if isinstance(ident, bool) or not isinstance(ident, (str, int)) or ident in records:
            raise ValueError('invalid or duplicate record ID')
        a, b = record['start_ms'], record['end_ms']
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (a, b)) or a < 0 or b < a:
            raise ValueError('invalid record times')
        if not isinstance(record['text'], str):
            raise ValueError('record text must be preserved')
        records[ident] = record
    def has_basis(entry, key):
        return isinstance(entry.get(key), str) and bool(entry[key].strip())

    seen, mapped, pending = set(), set(), []
    by_cue = {c.number: c for c in cues}

    def claim(ids):
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or seen.intersection(ids) or any(i not in records for i in ids):
            raise ValueError('missing, duplicate or reused source records')
        seen.update(ids)
        return [records[i] for i in ids]

    for entry in source_map['cues']:
        n = entry['cue_number']
        if type(n) is not int or n not in by_cue or n in mapped:
            raise ValueError('unknown or repeated cue mapping')
        mapped.add(n)
        rs = claim(entry['record_ids'])
        cue = by_cue[n]
        if entry['before'] != ''.join(r['text'] for r in rs) or entry['after'] != '\n'.join(cue.lines):
            raise ValueError('source or final wording differs from mapping')
        if entry['before'] != entry['after'] and not has_basis(entry, 'reason'):
            raise ValueError('rewrite requires a reason')
        positive = [r for r in rs if r['end_ms'] > r['start_ms']]
        if not positive:
            pending.append({'cue_number': n, 'reason': 'no positive-duration source anchor'})
            continue
        if any(a['start_ms'] > b['start_ms'] for a, b in zip(rs, rs[1:])):
            raise ValueError('source records are not chronological')
        first, last = positive[0], positive[-1]
        if entry.get('start_anchor_id') != first['id'] or entry.get('end_anchor_id') != last['id']:
            pending.append({'cue_number': n, 'reason': 'anchor IDs are not real first/last phrase records'})
        if round(cue.start*1000) != first['start_ms'] or round(cue.end*1000) != last['end_ms']:
            pending.append({'cue_number': n, 'reason': 'cue boundaries differ from real source anchors'})
        if any(r['start_ms'] < first['start_ms'] or r['end_ms'] > last['end_ms'] for r in rs):
            pending.append({'cue_number': n, 'reason': 'record falls outside phrase anchors'})
        if any(r['start_ms'] == r['end_ms'] for r in rs) and not has_basis(entry, 'zero_duration_binding_basis'):
            pending.append({'cue_number': n, 'reason': 'zero-duration content needs an explicit phrase-binding basis'})
    for omission in source_map.get('omissions', []):
        claim(omission['record_ids'])
        if not has_basis(omission, 'reason'):
            raise ValueError('omission needs a reason')
        if omission.get('status') not in ('omitted', 'pending'):
            raise ValueError('omission must explicitly be omitted or pending')
        if omission['status'] == 'pending':
            pending.append({'record_ids': omission['record_ids'], 'reason': omission['reason']})
    missing = [i for i in records if i not in seen]
    if missing:
        pending.append({'record_ids': missing, 'reason': 'unaccounted source content'})
    if mapped != set(by_cue):
        errors.append('not every cue has source lineage')
    return {'ok': not errors and not pending, 'errors': errors, 'pending': pending,
            'source_records': len(records), 'mapped_cues': len(mapped),
            'zero_duration_records': sum(r['start_ms'] == r['end_ms'] for r in records.values()),
            'semantic_review_completed_by_tool': False, 'human_full_audio_review': False,
            'new_word_timestamps_generated': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--srt', type=Path, required=True)
    p.add_argument('--source-map', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    guard_path(args.output, args.srt, args.source_map)
    try:
        report = audit_sources(args.srt.read_text(encoding='utf-8-sig'), json.loads(args.source_map.read_text()))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report = {'ok': False, 'errors': [str(exc)]}
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
