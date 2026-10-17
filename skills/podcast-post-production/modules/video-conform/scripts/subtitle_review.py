#!/usr/bin/env python3
"""Local subtitle review: scan numbers, build contextual clips, serve decisions, apply a snapshot."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import threading
import tempfile
import unicodedata
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.files import outside_package, distinct_output, child_output

from subtitle_policy import numeric_literals, mask_literals, format_policy, validate_exceptions
from validate_srt import Cue, parse_srt, validate_srt, video_duration

SCHEMA = 1
DECISIONS = (None, 'accept', 'edit', 'uncertain')
NUMBERS = re.compile(r'\d+(?:[.点]\d+)?(?:%|％|‰)?|第[零〇一二三四五六七八九十百千万亿两]+|[零〇一二三四五六七八九十百千万亿两]+(?:分之[零〇一二三四五六七八九十百千万亿两]+|年代|厘米|毫米|公里|年|月|日|岁|米|斤|两|克|元|成|个|次|倍|分|秒|万|亿|人|名|位|家|户|件|份|套|块|页|章|期|滴|项)?')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def manifest_hash(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def guarded_file(path, *, root=None):
    path = outside_package(path)
    if root is not None:
        base = Path(root).resolve()
        resolved = path.resolve()
        if resolved == base or base not in resolved.parents:
            raise ValueError('Review file escapes work directory')
    if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        raise ValueError('Review file must be a private regular file, not a hardlink')
    return path


def review_files(workdir):
    workdir = outside_package(workdir).resolve()
    paths = [guarded_file(workdir / name, root=workdir) for name in
             ('baseline.srt', 'manifest.json', 'decisions.json')]
    return workdir, paths


def write_json(path, data):
    path = guarded_file(path)
    # Create a unique exclusive sibling, never write through a pre-existing temp alias.
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        guarded_file(path)
        os.replace(temp, path)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


def read_cues(path):
    cues, errors = parse_srt(Path(path).read_text(encoding='utf-8-sig'))
    if errors or [c.number for c in cues] != list(range(1, len(cues) + 1)):
        raise ValueError(f'invalid baseline: {errors or "duplicate or nonsequential cue numbers"}')
    return cues


def safe_evidence(value):
    if not isinstance(value, str):
        raise ValueError('evidence must be selected plain transcript text, not a raw response')
    return re.sub(r'https?://\S+', '[链接已省略]', value)


def normalize_compact(text, protected_terms=(), *, numeric_style='spoken', approved_literals=()):
    """Convert unambiguous numeric notation BEFORE punctuation removal. Do not infer facts."""
    numeric_literals('', numeric_style)
    if numeric_style == 'arabic' or approved_literals:
        lines = text.splitlines()
        check_sign = '\n'.join(line[1:] for line in lines) if len(lines) == 2 and all(line.startswith('-') for line in lines) else text
        if numeric_style == 'arabic' and re.search(r'(?<!\d)[-−–－﹣]\d', mask_literals(check_sign, approved_literals)):
            raise ValueError('negative number requires an explicit reviewed literal')
        literals = list(approved_literals) + [t for t in numeric_literals(text, numeric_style) if any(c in t for c in '.．%％‰')]
        mask_literals(text, literals)  # validate tokens before masking
        masked, restore = text, {}
        for i, literal in enumerate(sorted(set(literals), key=len, reverse=True)):
            token = 'LITERAL' + chr(65+i//26) + chr(65+i%26) + 'TOKEN'
            if token in text:
                raise ValueError('literal marker collision')
            restore[token] = literal
            masked = masked.replace(literal, token)
        if numeric_style == 'arabic' and (re.search(r'[%‰/]|\d\s*[:：~～—–－-]\s*\d', masked)):
            raise ValueError('ambiguous numeric notation needs review')
        safe_terms = [t for t in protected_terms if t not in literals]
        result = normalize_compact(masked, safe_terms)
        for token, literal in restore.items():
            result = result.replace(token, literal)
        return result
    if any(t in text and any(unicodedata.category(c)[0] in 'PS' for c in t) for t in protected_terms):
        raise ValueError('protected term needs a documented punctuation exception')
    raw_lines = text.splitlines()
    dual_prefix = len(raw_lines) == 2 and all(line.startswith('-') for line in raw_lines)
    if dual_prefix:
        text = '\n'.join(line[1:] for line in raw_lines)
    protected = {}
    for i, term in enumerate(sorted(protected_terms, key=len, reverse=True)):
        if not term:
            raise ValueError('protected terms cannot be empty')
        token = f'PROTECTEDTERM{i}TOKEN'
        if token in text:
            raise ValueError('protected marker collision')
        if term in text:
            protected[token] = term
            text = text.replace(term, token)
    text = re.sub(r'(?<![\d.．])(\d+)[.．](\d+)(?![\d.．])', r'\1点\2', text)
    text = re.sub(r'(\d+(?:点\d+)?)[%％]', r'百分之\1', text)
    def fraction(m):
        if float(m[2].replace('点', '.')) == 0:
            raise ValueError('zero denominator needs review')
        return m[2] + '分之' + m[1]
    text = re.sub(r'(?<![\d/点])(\d+(?:点\d+)?)\s*/\s*(\d+(?:点\d+)?)(?![\d/点])', fraction, text)
    if re.search(r'比例|比值|比为|配比', text):
        text = re.sub(r'(\d+)\s*[:：]\s*(\d+)', r'\1比\2', text)
    if ('/' in text or
        re.search(r'\d\s*[-+*.,，、;；…:：=×÷~～—–－]+\s*\d|\d\.(?!\d)|\.\d|(?<!\d)[-−–－﹣]\d', text) or
        re.search(r'\d[ \t]*[^\w\s]+[ \t]*\d|[A-Za-z][+#@]', text) or
        (re.search(r'\d|[A-Za-z]', text) and any(unicodedata.category(c)[0] == 'S' for c in text))):
        raise ValueError('ambiguous numeric symbol or time/date notation; request review instead of stripping')
    lines = []
    for line in text.splitlines():
        prefix = '-' if dual_prefix or line.startswith('-') else ''
        content = line[1:] if line.startswith('-') else line
        lines.append(prefix + ''.join(c for c in content if unicodedata.category(c)[0] not in 'PSC').strip())
    result = '\n'.join(lines)
    for token, term in protected.items():
        result = result.replace(token, term)
    return result


def scan_numbers(srt, protected_terms=()):
    results = []
    for cue in read_cues(srt):
        text = ''.join(cue.lines)
        masked = text
        for term in sorted(protected_terms, key=len, reverse=True):
            if not term:
                raise ValueError('protected terms cannot be empty')
            masked = masked.replace(term, ' ' * len(term))
        mentions = [m.group() for m in NUMBERS.finditer(masked)]
        if mentions:
            results.append(dict(cue_numbers=[cue.number], kind='numeric', priority=False,
                                question='核对数字 单位 范围及所指人群或阶段', mentions=mentions,
                                original_text=text, suggested_text=text, unit_note='', needs_review=True,
                                start_ms=round(cue.start*1000), end_ms=round(cue.end*1000)))
    return results


def build_review(srt, items, workdir, *, audio=None, media_duration=None, profile=None,
                 context_seconds=5.0, protected_terms=(), validation_overrides=None,
                 numeric_style='spoken', numeric_review='uncertain', format_exceptions=None):
    outside_package(workdir)
    distinct_output(workdir, srt, *([audio] if audio else []))
    srt, workdir = Path(srt).resolve(), Path(workdir).resolve()
    cues = read_cues(srt)
    duration = video_duration(Path(audio)) if audio else media_duration
    if duration is None or context_seconds < 0:
        raise ValueError('audio or media duration is required; context seconds must be nonnegative')
    structural = validate_srt(srt.read_text(encoding='utf-8-sig'), media_duration=duration,
                              max_chars=10**9, enforce_house_style=False)
    if not structural['ok']:
        raise ValueError(str(structural['errors']))
    numeric_literals('', numeric_style)
    if numeric_review not in ('all', 'uncertain'):
        raise ValueError('unknown numeric review scope')
    numeric_candidates = scan_numbers(srt, protected_terms)
    if numeric_review == 'all':
        covered = {n for item in items for n in item['cue_numbers']}
        items = list(items) + [dict(item, id=f'numeric-{item["cue_numbers"][0]}')
                               for item in numeric_candidates if item['cue_numbers'][0] not in covered]
    baseline_hash = sha(srt)
    baseline_text = srt.read_text(encoding='utf-8-sig')
    validate_exceptions(baseline_text, cues, format_exceptions)
    validation_overrides = dict(validation_overrides or {})
    if set(validation_overrides) - {'max_chars', 'max_lines', 'max_screen_chars', 'enforce_house_style'}:
        raise ValueError('unknown style override')
    # Validate configured limits even when the baseline itself still needs proofreading.
    validate_srt('1\n00:00:00,000 --> 00:00:00,001\n字\n',
                 media_duration=duration, profile=profile, **validation_overrides)
    if not items:
        raise ValueError('review requires at least one item')
    manifest_items, seen = [], set()
    for index, item in enumerate(items, 1):
        numbers = item['cue_numbers']
        if not numbers or any(type(n) is not int or not 1 <= n <= len(cues) for n in numbers) or len(set(numbers)) != len(numbers):
            raise ValueError('invalid or duplicate cue targets')
        numbers = sorted(numbers)
        operation = item.get('operation', 'replace')
        if operation not in ('replace', 'merge'):
            raise ValueError('unknown review operation')
        if operation == 'merge' and (len(numbers) < 2 or numbers != list(range(numbers[0], numbers[-1]+1))):
            raise ValueError('merge requires contiguous explicitly targeted cues')
        suggested = item.get('suggested_text')
        if suggested is not None and not isinstance(suggested, str):
            raise ValueError('suggested text must be plain text')
        literals = item.get('format_literals', [])
        if not isinstance(literals, list):
            raise ValueError('format literals must be a list')
        if literals:
            if not suggested or any(not t or t not in suggested for t in literals):
                raise ValueError('format literals need exact proposed text')
            mask_literals(suggested, literals)
        ident = item.get('id') or 'review-' + hashlib.sha256((baseline_hash + ':' + ','.join(map(str, numbers)) + ':' + str(index)).encode()).hexdigest()[:16]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in seen:
            raise ValueError('invalid or duplicate review ID')
        seen.add(ident)
        targets = [dict(cue_number=n, before_lines=list(cues[n-1].lines),
                        start_ms=round(cues[n-1].start*1000), end_ms=round(cues[n-1].end*1000)) for n in numbers]
        evidence = {str(k): safe_evidence(v) for k, v in item.get('evidence', {}).items()}
        prior = item.get('prior_confirmation')
        if prior is not None and (not isinstance(prior, str) or not prior.strip()):
            raise ValueError('prior confirmation requires an actual basis')
        start = max(0.0, min(cues[n-1].start for n in numbers) - context_seconds)
        end = min(duration, max(cues[n-1].end for n in numbers) + context_seconds)
        manifest_items.append(dict(id=ident, targets=targets,
                                   current_text='\n\n'.join('\n'.join(cues[n-1].lines) for n in numbers),
                                   context_before=[''.join(c.lines) for c in cues[max(0,numbers[0]-3):numbers[0]-1]],
                                   context_after=[''.join(c.lines) for c in cues[numbers[-1]:numbers[-1]+2]],
                                   question=safe_evidence(item.get('question', '请核对这一处')),
                                   kind=item.get('kind', 'text'), priority=bool(item.get('priority')),
                                   numeric_cue_numbers=[n for n in numbers if any(n in x['cue_numbers'] for x in numeric_candidates)],
                                   operation=operation, suggested_text=safe_evidence(suggested) if suggested is not None else None,
                                   unit_note=safe_evidence(item.get('unit_note', '')),
                                   original_text=safe_evidence(item.get('original_text', '\n\n'.join('\n'.join(cues[n-1].lines) for n in numbers))),
                                   group_label=safe_evidence(item.get('group_label', '')),
                                   format_literals=literals,
                                   evidence=evidence, prior_confirmation=prior,
                                   clip_start=start, clip_end=end,
                                   audio=f'audio/{ident}.mp3' if audio else None))
    workdir.mkdir(parents=True, exist_ok=False)
    (workdir/'baseline.srt').write_bytes(srt.read_bytes())
    manifest = dict(schema_version=SCHEMA, baseline_sha256=baseline_hash, source_path=str(srt),
                    media_duration=duration, profile=profile, validation_overrides=validation_overrides,
                    protected_terms=list(protected_terms), items=manifest_items,
                    audio_source_path=str(Path(audio).resolve()) if audio else None,
                    audio_source_sha256=sha(audio) if audio else None,
                    numeric_style=numeric_style, numeric_review=numeric_review,
                    numeric_candidates=numeric_candidates, format_exceptions=format_exceptions)
    write_json(workdir/'manifest.json', manifest)
    state = dict(schema_version=SCHEMA, baseline_sha256=baseline_hash, revision=0, items=[
        dict(id=x['id'], decision='accept' if x['prior_confirmation'] else None,
             corrected_text=x['current_text'], note=x['prior_confirmation'] or '',
             action_source='prior_confirmation' if x['prior_confirmation'] else None)
        for x in manifest_items])
    write_json(workdir/'decisions.json', state)
    if audio:
        (workdir/'audio').mkdir()
        for item in manifest_items:
            output = child_output(workdir, item['audio'], srt, audio)
            guarded_file(output, root=workdir)
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(Path(audio).resolve()),
                            '-ss', str(item['clip_start']), '-t', str(item['clip_end']-item['clip_start']),
                            '-vn', '-ac', '1', '-ar', '24000', '-b:a', '64k', str(output)], check=True)
            item['audio_sha256'] = sha(output)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'], check=True)
        write_json(workdir/'manifest.json', manifest)
    state['manifest_sha256'] = manifest_hash(manifest)
    write_json(workdir/'decisions.json', state)
    return manifest


def validate_state(manifest, state):
    if state.get('schema_version') != SCHEMA or state.get('baseline_sha256') != manifest['baseline_sha256'] or state.get('manifest_sha256') != manifest_hash(manifest):
        raise ValueError('review snapshot belongs to another baseline')
    rows = state.get('items', [])
    ids = [x.get('id') for x in rows]
    if len(ids) != len(set(ids)) or set(ids) != {x['id'] for x in manifest['items']}:
        raise ValueError('missing, duplicate, or unknown review IDs')
    if type(state.get('revision')) is not int or state['revision'] < 0:
        raise ValueError('invalid revision')
    for row in rows:
        if row.get('decision') not in DECISIONS or not isinstance(row.get('corrected_text'), str) or not isinstance(row.get('note'), str):
            raise ValueError('invalid decision or text')
        if row['decision'] == 'edit' and not row['corrected_text'].strip():
            raise ValueError('edit requires text')
        if row.get('action_source') not in (None, 'individual', 'explicit_bulk', 'prior_confirmation'):
            raise ValueError('invalid action source')
        if row.get('action_source') == 'prior_confirmation' and not next(x for x in manifest['items'] if x['id'] == row['id'])['prior_confirmation']:
            raise ValueError('prior confirmation has no basis')


def render_srt(cues):
    def stamp(seconds):
        value = round(seconds * 1000)
        secs, ms = divmod(value, 1000)
        mins, secs = divmod(secs, 60)
        hrs, mins = divmod(mins, 60)
        return f'{hrs:02}:{mins:02}:{secs:02},{ms:03}'
    return ''.join(f'{c.number}\n{stamp(c.start)} --> {stamp(c.end)}\n' + '\n'.join(c.lines) + '\n\n' for c in cues)


def apply_review(workdir, output, *, source=None):
    workdir, private_inputs = review_files(workdir)
    output = outside_package(output)
    manifest = load(workdir/'manifest.json')
    state_bytes = (workdir/'decisions.json').read_bytes()
    state = json.loads(state_bytes)
    validate_state(manifest, state)
    baseline = workdir/'baseline.srt'
    protected = [*private_inputs, Path(source or manifest['source_path'])]
    if manifest.get('audio_source_path'):
        protected.append(Path(manifest['audio_source_path']))
    distinct_output(output, *protected)
    audit_path = outside_package(output.with_suffix('.review'))
    distinct_output(audit_path, *protected, output)
    if sha(baseline) != manifest['baseline_sha256'] or sha(source or manifest['source_path']) != manifest['baseline_sha256']:
        raise ValueError('baseline changed; rebuild or explicitly reconcile review')
    if manifest.get('audio_source_path') and sha(manifest['audio_source_path']) != manifest['audio_source_sha256']:
        raise ValueError('review source audio changed; rebuild review clips')
    if output.exists() or output.with_suffix('.review').exists():
        raise FileExistsError('refusing existing output or audit directory')
    cues = read_cues(baseline)
    items = {x['id']: x for x in manifest['items']}
    original = list(cues)
    baseline_text = baseline.read_text(encoding='utf-8-sig')
    existing_exceptions = validate_exceptions(baseline_text, cues, manifest.get('format_exceptions'))
    exception_rows = {e['cue_number']: e for e in (manifest.get('format_exceptions') or {}).get('entries', [])}
    removed, merged_origins = set(), {}
    occupied, confirmed, changes, pending, ledger = set(), set(), [], [], []
    for response in state['items']:
        item = items[response['id']]
        numbers = [t['cue_number'] for t in item['targets']]
        if len(numbers) != len(set(numbers)):
            raise ValueError('duplicate target in manifest')
        for target in item['targets']:
            original_target = original[target['cue_number']-1]
            if (list(original_target.lines) != target['before_lines'] or round(original_target.start*1000) != target['start_ms'] or round(original_target.end*1000) != target['end_ms']):
                raise ValueError('target no longer matches baseline')
        row = dict(id=item['id'], cue_numbers=numbers, decision=response['decision'],
                   action_source=response.get('action_source'), note=response['note'])
        if response['decision'] in ('accept', 'edit'):
            if occupied.intersection(numbers):
                raise ValueError('overlapping selected review targets; reconcile before applying')
            occupied.update(numbers)
        if response['decision'] == 'edit':
            blocks = re.split(r'\n[ \t]*\n', response['corrected_text'].strip())
            replacements = []
            try:
                merge = item.get('operation') == 'merge'
                if merge and numbers != list(range(numbers[0], numbers[-1]+1)):
                    raise ValueError('merge requires adjacent targets')
                targets = [numbers[0]] if merge else numbers
                if len(blocks) != len(targets):
                    raise ValueError('cue count changed; needs sentence splitting and real timing anchors')
                proposed_literals = item.get('format_literals', [])
                if proposed_literals and response['corrected_text'].strip() != item.get('suggested_text'):
                    raise ValueError('format exception text differs from reviewed proposal')
                if proposed_literals and len(targets) != 1:
                    raise ValueError('format exceptions require one replacement or merge result')
                for n, block in zip(targets, blocks):
                    allowed = list(proposed_literals)
                    if block == '\n'.join(original[n-1].lines):
                        allowed += existing_exceptions.get(n, [])
                    if manifest['profile'] == 'compact-clean' and manifest['validation_overrides'].get('enforce_house_style', True):
                        block = normalize_compact(block, manifest['protected_terms'],
                                                  numeric_style=manifest.get('numeric_style', 'spoken'), approved_literals=allowed)
                    candidate = replace(original[n-1], end=original[numbers[-1]-1].end if merge else original[n-1].end, lines=tuple(block.splitlines()))
                    sample_text = render_srt([replace(candidate, number=1)])
                    local_exceptions = format_policy(sample_text, [dict(cue_number=1, text=block, literals=allowed,
                        approval_basis='submitted edit in frozen review snapshot')]) if allowed else None
                    qa = validate_srt(sample_text, numeric_style=manifest.get('numeric_style', 'spoken'), format_exceptions=local_exceptions,
                                      media_duration=manifest['media_duration'], profile=manifest['profile'],
                                      **manifest['validation_overrides'])
                    if not qa['ok']:
                        raise ValueError('needs reflow or timing review: ' + '; '.join(qa['errors']))
                    replacements.append((n, candidate, allowed))
            except ValueError as exc:
                row['status'] = 'pending_reflow_or_timing'
                pending.append(dict(id=item['id'], reason=str(exc), submitted_text=response['corrected_text']))
            else:
                if merge:
                    removed.update(numbers[1:])
                    merged_origins[numbers[0]] = numbers
                    for old in numbers[1:]:
                        exception_rows.pop(old, None)
                for n, candidate, allowed in replacements:
                    exception_rows.pop(n, None)
                    if allowed:
                        exception_rows[n] = dict(cue_number=n, text='\n'.join(candidate.lines), literals=allowed,
                                                approval_basis='submitted edit in frozen review snapshot')
                    changes.append(dict(cue_number=n, before=list(cues[n-1].lines), after=list(candidate.lines),
                                        start=candidate.start, end=candidate.end, submitted_text=response['corrected_text'],
                                        timing_basis='union of original adjacent phrase boundaries; no new word timestamps' if merge else 'unchanged original phrase boundaries; no new word timestamps',
                                        original_cues=[dict(cue_number=k, text='\n'.join(original[k-1].lines), start=original[k-1].start, end=original[k-1].end) for k in (numbers if merge else [n])],
                                        original_cue_numbers=numbers if merge else [n], original_start=original[n-1].start,
                                        original_end=original[numbers[-1]-1].end if merge else original[n-1].end))
                    cues[n-1] = candidate
                confirmed.update(numbers)
                row['status'] = 'applied_edit'
        elif response['decision'] == 'uncertain':
            row['status'] = 'awaiting_listening'
            pending.append(dict(id=item['id'], reason=response['note'] or '用户拿不准'))
        else:
            if response['decision'] == 'accept':
                confirmed.update(numbers)
            row['status'] = 'confirmed_unchanged' if response['decision'] == 'accept' else 'unselected_retained'
        ledger.append(row)
    final, cue_map, final_exceptions = [], [], []
    for old, cue in enumerate(cues, 1):
        if old in removed:
            continue
        new = len(final)+1
        final.append(replace(cue, number=new))
        cue_map.extend(dict(old_cue=n, new_cue=new) for n in merged_origins.get(old, [old]))
        if old in exception_rows:
            final_exceptions.append(dict(exception_rows[old], cue_number=new))
    text = render_srt(final)
    output_policy = format_policy(text, final_exceptions)
    report = validate_srt(text, numeric_style=manifest.get('numeric_style', 'spoken'), format_exceptions=output_policy, media_duration=manifest['media_duration'], profile=manifest['profile'],
                          **manifest['validation_overrides'])
    numeric_candidates = manifest.get('numeric_candidates')
    if numeric_candidates is None:
        numeric_candidates = scan_numbers(baseline, manifest.get('protected_terms', []))
    numeric_unconfirmed = [n for x in numeric_candidates for n in x['cue_numbers'] if n not in confirmed]
    report.update(all_numbers_human_confirmed=not numeric_unconfirmed and not pending,
                  decision_counts=dict(Counter(x['decision'] or 'unselected' for x in state['items'])),
                  prior_confirmation_count=sum(x.get('action_source') == 'prior_confirmation' and x['decision'] == 'accept' for x in state['items']),
                  all_items_human_confirmed=all(x['decision'] in ('accept','edit') for x in state['items']) and not pending,
                  human_full_audio_review=False, semantic_review_completed_by_tool=False,
                  cue_map=cue_map, numeric_review=manifest.get('numeric_review', 'uncertain'),
                  numeric_unconfirmed_cues=numeric_unconfirmed,
                  model_calls_performed_by_tool=False, pending=pending, changes=changes,
                  status='review_draft' if pending else 'submitted_decisions_applied',
                  new_asr_calls=0, baseline_sha256=manifest['baseline_sha256'],
                  review_snapshot_sha256=hashlib.sha256(state_bytes).hexdigest())
    if not report['ok']:
        raise ValueError('output validation failed: ' + '; '.join(report['errors']))
    audit = output.with_suffix('.review')
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.mkdir(exist_ok=False)
    (audit/'submitted-decisions.json').write_bytes(state_bytes)
    write_json(audit/'manifest.json', manifest)
    write_json(audit/'ledger.json', ledger)
    write_json(audit/'cue-map.json', cue_map)
    write_json(audit/'format-exceptions.json', output_policy)
    write_json(audit/'qa.json', report)
    # Exclusive creation protects an existing version, even against a concurrent writer.
    with output.open('x', encoding='utf-8') as handle:
        handle.write(text)
    report['output_sha256'] = sha(output)
    write_json(audit/'qa.json', report)
    return report


PAGE = '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>字幕复听确认</title>
<style>body{font:17px system-ui;max-width:960px;margin:30px auto;padding:0 18px;background:#f5f5f2;color:#222}header{position:sticky;top:0;background:#f5f5f2;padding:12px 0}article{background:white;padding:22px;margin:18px 0;border-radius:12px}pre{white-space:pre-wrap;line-height:1.7}textarea{width:95%;min-height:85px;font:inherit}button,select{font:inherit;margin:6px;padding:8px}audio{width:100%}.context{color:#666;font-size:15px}.badge{color:#8a4c00}</style>
<header><h1>字幕复听确认</h1><p id="counts"></p><select id="filter"><option value="all">全部</option><option value="priority">重点项</option><option value="numeric">数字项</option><option value="pending">未选择</option><option value="uncertain">拿不准</option><option value="done">已处理</option></select><button id="bulk">确认全部未选择项采用当前文字</button><button id="save">保存结论</button><span id="status"></span></header><main id="list"></main>
<script>
let manifest,state,queue=Promise.resolve();const $=id=>document.getElementById(id);
function time(ms){const s=Math.floor(ms/1000);return `${Math.floor(s/3600).toString().padStart(2,'0')}:${Math.floor(s/60)%60<10?'0':''}${Math.floor(s/60)%60}:${(s%60).toString().padStart(2,'0')}.${(ms%1000).toString().padStart(3,'0')}`}
function el(tag,text){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;return x}
function stats(){const c={};state.items.forEach(x=>{const k=x.decision||'未选择';c[k]=(c[k]||0)+1});$('counts').textContent=`总计 ${state.items.length} 项　保留 ${c.accept||0}　修改 ${c.edit||0}　拿不准 ${c.uncertain||0}　未选择 ${c['未选择']||0}　历史确认 ${state.items.filter(x=>x.action_source==='prior_confirmation'&&x.decision==='accept').length}`}
function save(){queue=queue.then(async()=>{const payload=JSON.parse(JSON.stringify(state));$('status').textContent='保存中';const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||'保存失败');state.revision=data.revision;$('status').textContent='已保存';}).catch(e=>{$('status').textContent='未保存 '+e.message;});return queue}
function render(){stats();$('list').replaceChildren();manifest.items.forEach(item=>{const row=state.items.find(x=>x.id===item.id),f=$('filter').value;if(f==='numeric'&&item.kind!=='numeric'&&!item.numeric_cue_numbers?.length||f==='priority'&&!item.priority||f==='pending'&&row.decision!==null||f==='uncertain'&&row.decision!=='uncertain'||f==='done'&&!['accept','edit'].includes(row.decision))return;const card=el('article');card.append(el('h2',item.id+'　字幕 '+item.targets.map(x=>x.cue_number).join('、')));card.append(el('p',item.targets.map(x=>time(x.start_ms)+' 至 '+time(x.end_ms)).join('　')));if(item.priority)card.append(el('p','重点核对'));card.append(el('p',item.question));if(item.operation==='merge')card.append(el('p','合并相邻字幕 使用修改文字后保留首尾真实时间'));if(item.group_label)card.append(el('p','分组 '+item.group_label+' 每处单独确认'));if(item.original_text)card.append(el('pre','原文（缺少来源时为字幕底稿） '+item.original_text));if(item.suggested_text!==null&&item.suggested_text!==undefined)card.append(el('pre','建议 '+item.suggested_text));if(item.unit_note)card.append(el('p','单位及语义 '+item.unit_note));if(item.format_literals?.length)card.append(el('p','精确格式例外 '+item.format_literals.join(' ')));const ctx=el('p','前文 '+item.context_before.join('　'));ctx.className='context';card.append(ctx,el('pre',item.current_text));if(item.audio){const a=el('audio');a.controls=true;a.preload='none';a.src='/'+item.audio;card.append(a)}const after=el('p','后文 '+item.context_after.join('　'));after.className='context';card.append(after);if(item.prior_confirmation)card.append(el('p','历史确认依据 '+item.prior_confirmation));const details=el('details');details.append(el('summary','识别证据'));Object.entries(item.evidence).forEach(([k,v])=>details.append(el('h3',k),el('pre',v)));card.append(details);const edit=el('textarea');edit.value=row.corrected_text;edit.setAttribute('aria-label','修改后的字幕 多条字幕之间留一个空行');edit.oninput=()=>{row.corrected_text=edit.value;save()};card.append(edit);['accept','edit','uncertain'].forEach((v,i)=>{const b=el('button',['保留当前文字','使用修改文字','拿不准'][i]);b.setAttribute('aria-pressed',String(row.decision===v));b.onclick=()=>{row.decision=v;row.action_source='individual';stats();save();card.querySelectorAll('button[aria-pressed]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)))};card.append(b)});const clear=el('button','撤销选择');clear.onclick=()=>{row.decision=null;row.action_source=null;render();save()};card.append(clear);const note=el('textarea');note.value=row.note;note.placeholder='备注或疑问';note.setAttribute('aria-label','备注');note.oninput=()=>{row.note=note.value;save()};card.append(note);$('list').append(card)})}
$('filter').onchange=render;$('save').onclick=save;$('bulk').onclick=()=>{if(!confirm('这会确认全部未选择项目采用当前文字 请确认确实已核对'))return;state.items.forEach(x=>{if(x.decision===null){x.decision='accept';x.action_source='explicit_bulk'}});render();save()};
fetch('/api/state').then(r=>r.json()).then(d=>{manifest=d.manifest;state=d.state;render()}).catch(e=>$('status').textContent='读取失败 '+e.message);
</script></html>'''


def make_server(workdir, port=0):
    workdir, private_inputs = review_files(workdir)
    manifest = load(workdir/'manifest.json')
    validate_state(manifest, load(workdir/'decisions.json'))
    lock = threading.Lock()
    if sha(workdir/'baseline.srt') != manifest['baseline_sha256']:
        raise ValueError('review baseline changed')
    if sha(manifest['source_path']) != manifest['baseline_sha256']:
        raise ValueError('review source changed')
    if manifest.get('audio_source_path') and sha(manifest['audio_source_path']) != manifest['audio_source_sha256']:
        raise ValueError('review source audio changed')
    frozen_manifest_sha256 = sha(workdir/'manifest.json')
    def audio_signature():
        if not manifest.get('audio_source_path'):
            return None
        value = Path(manifest['audio_source_path']).stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    frozen_audio_identity = audio_signature()

    def check_snapshot():
        review_files(workdir)
        if sha(workdir/'manifest.json') != frozen_manifest_sha256 or sha(workdir/'baseline.srt') != manifest['baseline_sha256'] or sha(manifest['source_path']) != manifest['baseline_sha256']:
            raise ValueError('review source or manifest changed; rebuild or reconcile')
        # Full source hash is verified on opening and applying; stat identity detects
        # runtime changes without re-reading hours of audio on each UI autosave.
        if audio_signature() != frozen_audio_identity:
            raise ValueError('review source audio changed; rebuild review clips')
        validate_state(manifest, load(workdir/'decisions.json'))

    audio = {}
    for item in manifest['items']:
        if item['audio']:
            path = guarded_file(workdir/item['audio'], root=workdir)
            if sha(path) != item['audio_sha256']:
                raise ValueError('review audio changed')
            audio['/' + item['audio']] = (path, item['audio_sha256'])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, data):
            self.send(status, json.dumps(data, ensure_ascii=False).encode())

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.json(403, {'error': 'invalid host'})
            path = urlparse(self.path).path
            if path == '/':
                return self.send(200, PAGE.encode(), 'text/html; charset=utf-8')
            if path == '/api/state':
                try:
                    with lock:
                        check_snapshot()
                        state = load(workdir/'decisions.json')
                    return self.json(200, dict(manifest=manifest, state=state))
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    return self.json(409, {'error': str(exc)})
            if path in audio:
                try:
                    clip, digest = audio[path]
                    guarded_file(clip, root=workdir)
                    if sha(clip) != digest:
                        raise ValueError('review audio changed')
                    return self.send(200, clip.read_bytes(), 'audio/mpeg')
                except (ValueError, OSError):
                    return self.json(403, {'error': 'invalid review audio'})
            self.json(404, {'error': 'not found'})

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != origin:
                return self.json(403, {'error': 'invalid origin'})
            if self.path != '/api/save':
                return self.json(404, {'error': 'not found'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 1024*1024:
                    raise ValueError('invalid request length')
                incoming = json.loads(self.rfile.read(length))
                validate_state(manifest, incoming)
                with lock:
                    check_snapshot()
                    current = load(workdir/'decisions.json')
                    if incoming['revision'] != current['revision']:
                        return self.json(409, {'error': '另一页面已保存更新 请刷新后再提交'})
                    incoming['revision'] += 1
                    previous = {x['id']: x for x in current['items']}
                    now = datetime.now(timezone.utc).isoformat()
                    for row in incoming['items']:
                        old = previous[row['id']]
                        row['reviewed_at'] = now if any(row.get(k) != old.get(k) for k in ('decision','corrected_text','note')) else old.get('reviewed_at')
                    # Only keep the declared fields; no raw responses or unknown metadata.
                    incoming = dict(schema_version=SCHEMA, baseline_sha256=manifest['baseline_sha256'],
                                    manifest_sha256=manifest_hash(manifest), saved_at=now,
                                    revision=incoming['revision'], items=[{k: x.get(k) for k in
                                    ('id','decision','corrected_text','note','action_source','reviewed_at')} for x in incoming['items']])
                    write_json(workdir/'decisions.json', incoming)
                self.json(200, {'revision': incoming['revision']})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.json(400, {'error': str(exc)})
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('scan-numbers')
    scan.add_argument('--srt', type=Path, required=True)
    scan.add_argument('--output', type=Path, required=True)
    scan.add_argument('--protected-term', action='append', default=[])
    build = sub.add_parser('build')
    build.add_argument('--srt', type=Path, required=True)
    build.add_argument('--items', type=Path, required=True)
    build.add_argument('--workdir', type=Path, required=True)
    build.add_argument('--audio', type=Path)
    build.add_argument('--media-duration', type=float)
    build.add_argument('--profile', choices=['compact-clean'])
    build.add_argument('--context-seconds', type=float, default=5.0)
    build.add_argument('--protected-term', action='append', default=[])
    build.add_argument('--max-chars', type=int)
    build.add_argument('--max-lines', type=int)
    build.add_argument('--max-screen-chars', type=int)
    build.add_argument('--numeric-style', choices=['spoken', 'arabic'], default='spoken')
    build.add_argument('--numeric-review', choices=['all', 'uncertain'], default='uncertain')
    build.add_argument('--format-exceptions', type=Path)
    build.add_argument('--allow-punctuation', action='store_true')
    serve = sub.add_parser('serve')
    serve.add_argument('--workdir', type=Path, required=True)
    serve.add_argument('--port', type=int, default=0)
    apply = sub.add_parser('apply')
    apply.add_argument('--workdir', type=Path, required=True)
    apply.add_argument('--output', type=Path, required=True)
    apply.add_argument('--source', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'scan-numbers':
            outside_package(args.output)
            distinct_output(args.output, args.srt)
            candidates = scan_numbers(args.srt, args.protected_term)
            with args.output.open('x', encoding='utf-8') as out:
                out.write(json.dumps(candidates, ensure_ascii=False, indent=2)+'\n')
        elif args.command == 'build':
            result = build_review(args.srt, load(args.items), args.workdir, audio=args.audio,
                                  media_duration=args.media_duration, profile=args.profile,
                                  numeric_style=args.numeric_style, numeric_review=args.numeric_review,
                                  format_exceptions=load(args.format_exceptions) if args.format_exceptions else None,
                                  context_seconds=args.context_seconds, protected_terms=args.protected_term,
                                  validation_overrides={**{k: getattr(args, k) for k in
                                  ('max_chars','max_lines','max_screen_chars') if getattr(args, k) is not None},
                                  **({'enforce_house_style': False} if args.allow_punctuation else {})})
            print(json.dumps({'items': len(result['items']), 'workdir': str(args.workdir)}))
        elif args.command == 'serve':
            server = make_server(args.workdir, args.port)
            print(f'http://127.0.0.1:{server.server_port}/', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:
            report = apply_review(args.workdir, args.output, source=args.source)
            print(json.dumps({k: report[k] for k in ('ok','status','decision_counts','all_items_human_confirmed')}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
