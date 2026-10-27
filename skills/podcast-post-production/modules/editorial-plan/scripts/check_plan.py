#!/usr/bin/env python3
"""Audit declared source-frame budgets and choices; never generate edits or approvals."""
from pathlib import Path
import argparse
import hashlib
import json
from fractions import Fraction
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.files import outside_package, distinct_output, file_identity

ACTIONS = {'keep', 'remove', 'insert', 'replace', 'move'}


def item_digest(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_context_digest(plan):
    return item_digest({'sources': plan.get('sources'), 'base': plan.get('base')})


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def union(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def audit(plan, directory):
    if plan.get('schema_version') != '1.0' or not plan.get('revision'):
        raise ValueError('Use planning schema_version 1.0 and a nonempty revision')
    directory = Path(directory)
    sources, checks, protected_paths = {}, [], []

    def evidence(ref):
        if not isinstance(ref, dict) or not ref.get('path') or not ref.get('sha256'):
            raise ValueError('Evidence requires path and sha256')
        path = Path(ref['path']).expanduser()
        path = path if path.is_absolute() else directory / path
        actual = file_identity(path)
        if actual['sha256'] != ref['sha256']:
            raise ValueError('Evidence fingerprint changed: ' + str(path))
        protected_paths.append(path)
        return actual

    for source in plan.get('sources', []):
        sid = source.get('id')
        if not isinstance(sid, str) or not sid or sid in sources:
            raise ValueError('Source IDs must be nonempty and unique')
        integer(source.get('sample_rate'), 'sample_rate', 1)
        integer(source.get('frames'), 'frames', 1)
        sources[sid] = source
        if source.get('path') or source.get('sha256'):
            checks.append({'id': sid, 'identity': evidence(source), 'status': 'hash_verified'})
        else:
            checks.append({'id': sid, 'status': 'declared_metadata_only'})
    base = plan['base']
    sid = base['source_id']
    if sid not in sources:
        raise ValueError('Unknown base source')
    rate = sources[sid]['sample_rate']

    def span(value, source_id=sid):
        if source_id not in sources:
            raise ValueError('Unknown range source')
        start = integer(value['start_frame'], 'start_frame')
        end = integer(value['end_frame'], 'end_frame', 1)
        if not start < end <= sources[source_id]['frames']:
            raise ValueError('Source range is empty or out of bounds')
        return [start, end]

    base_range = span(base)
    items = {}
    for item in plan.get('items', []):
        iid = item.get('id')
        if not isinstance(iid, str) or not iid or iid in items:
            raise ValueError('Item IDs must be nonempty and unique')
        if item.get('action') not in ACTIONS:
            raise ValueError('Unknown planning action')
        if not item.get('reason'):
            raise ValueError('Every item needs its reason/content-loss statement')
        if item['action'] in {'keep', 'remove', 'replace'}:
            a = span(item)
            if a[0] < base_range[0] or a[1] > base_range[1]:
                raise ValueError('Consumed/kept range must be inside the selected base')
        if item['action'] in {'insert', 'replace', 'move'}:
            segments = item.get('segments', [])
            if not segments:
                raise ValueError('Insertion/replacement/move requires recorded source segments')
            mode = item.get('block_mode', 'whole')
            if mode not in {'whole', 'fine'} or mode == 'whole' and len(segments) != 1:
                raise ValueError('Whole mode needs one contiguous source range; group it before planning')
            for seg in segments:
                span(seg, seg['source_id'])
            integer(item.get('buffer_frames', 0), 'buffer_frames')
            if item['action'] in {'insert', 'move'}:
                at = integer(item.get('at_frame'), 'at_frame')
                if not base_range[0] <= at <= base_range[1]:
                    raise ValueError('Destination outside selected base')
            if item['action'] == 'move':
                if len(segments) != 1 or segments[0]['source_id'] != sid:
                    raise ValueError('Move consumes one range on the selected base clock')
                a = span(segments[0])
                if a[0] < base_range[0] or a[1] > base_range[1] or a[0] <= item['at_frame'] < a[1]:
                    raise ValueError('Invalid move source or destination inside itself')
        items[iid] = item
    for item in items.values():
        if any(x not in items or x == item['id'] for x in item.get('requires', [])):
            raise ValueError('Unknown/self conditional item dependency')
    recommended = plan.get('recommended_ids', [])
    if len(set(recommended)) != len(recommended) or any(x not in items for x in recommended):
        raise ValueError('Recommended IDs must be unique known items')
    choices = plan.get('choices', {})
    if any(x not in items for x in choices):
        raise ValueError('Choice references an unknown item')
    confirmed, kept, custom, choice_evidence = set(), set(), [], []
    for iid, choice in choices.items():
        value = choice.get('choice')
        if value not in {'apply', 'keep', 'pending', 'custom'}:
            raise ValueError('Unknown choice')
        if value in {'apply', 'keep'}:
            if choice.get('item_sha256') != item_digest(items[iid]):
                raise ValueError('Choice is stale or unbound: ' + iid)
            if choice.get('source_context_sha256') != source_context_digest(plan):
                raise ValueError('Choice source/version binding changed: ' + iid)
            if value == 'apply':
                choice_evidence.append({'id': iid, 'identity': evidence(choice.get('review_ref'))})
                confirmed.add(iid)
            else:
                kept.add(iid)
        if value == 'custom':
            custom.append(iid)
    proposed = (set(recommended) | confirmed) - kept - set(custom)
    fixed = integer(plan.get('fixed_extra_frames', 0), 'fixed_extra_frames')
    transition = integer(plan.get('transition_overlap_frames', 0), 'transition_overlap_frames')
    protections = [span(x) for x in plan.get('protected_ranges', [])]
    protections += [span(items[i]) for i in confirmed if items[i]['action'] == 'keep']
    protections += [span(items[i]) for i in kept if items[i]['action'] in {'remove', 'replace', 'keep'}]
    protections += [span(items[i]['segments'][0]) for i in kept if items[i]['action'] == 'move']
    units = {}
    for unit in plan.get('units', []):
        uid = unit['id']
        if uid in units:
            raise ValueError('Duplicate content unit ID')
        a = span(unit)
        if a[0] < base_range[0] or a[1] > base_range[1]:
            raise ValueError('Content unit outside selected base')
        units[uid] = unit
    for u in units.values():
        if any(i not in units or i == u['id'] for i in u.get('depends_on', [])):
            raise ValueError('Unknown/self content dependency')

    def calculate(selected):
        removals, consumed, insertions, problems = [], [], [], []
        active_protections = protections + [span(items[i]) for i in selected if items[i]['action'] == 'keep']
        for iid in sorted(selected):
            item = items[iid]
            action = item['action']
            if any(x not in selected for x in item.get('requires', [])):
                problems.append({'id': iid, 'issue': 'conditional_dependency_missing'})
            a = None
            if action in {'remove', 'replace'}:
                a = span(item)
            elif action == 'move':
                a = span(item['segments'][0])
            if a:
                removals.append(a)
                consumed.append((iid, action, a))
                if any(overlap(a, p) for p in active_protections):
                    problems.append({'id': iid, 'issue': 'protected_or_kept_content_consumed'})
            if action in {'insert', 'replace', 'move'}:
                if item.get('block_mode', 'whole') == 'fine':
                    if not item.get('fine_review_ref'):
                        problems.append({'id': iid, 'issue': 'fine_edit_scope_unconfirmed'})
                    else:
                        evidence(item['fine_review_ref'])
                seconds = sum((Fraction(seg['end_frame'] - seg['start_frame'],
                             sources[seg['source_id']]['sample_rate']) for seg in item['segments']), Fraction())
                insertions.append({'id': iid, 'seconds': seconds,
                    'buffer': Fraction(2 * item.get('buffer_frames', 0), rate),
                    'at': item['start_frame'] if action == 'replace' else item['at_frame']})
        merged = union(removals)
        for i, (iid, action, a) in enumerate(consumed):
            for jid, other, b in consumed[i + 1:]:
                if overlap(a, b) and (action != 'remove' or other != 'remove'):
                    problems.append({'id': iid, 'other': jid, 'issue': 'overlapping_structural_operations'})
        for ins in insertions:
            if any(start < ins['at'] < end for start, end in merged):
                problems.append({'id': ins['id'], 'issue': 'destination_inside_removed_content'})
        remaining = {}
        for uid, unit in units.items():
            a = span(unit)
            # A moved/reused unit still exists in the proposed programme.
            restored = union([span(seg) for iid in selected
                              for seg in items[iid].get('segments', []) if seg['source_id'] == sid])
            still_removed = sum(overlap(a, cut) - sum(overlap([max(a[0], cut[0]), min(a[1], cut[1])], r)
                                for r in restored) for cut in merged if overlap(a, cut))
            remaining[uid] = a[1] - a[0] - still_removed
        for uid, unit in units.items():
            if remaining[uid] > 0:
                for needed in unit.get('depends_on', []):
                    if remaining[needed] == 0:
                        problems.append({'id': uid, 'requires_unit': needed, 'issue': 'dangling_reference'})
        removed = sum(end - start for start, end in merged)
        inserted = sum((a['seconds'] for a in insertions), Fraction())
        buffers = sum((a['buffer'] for a in insertions), Fraction())
        total = Fraction(base_range[1] - base_range[0] - removed + fixed - transition, rate) + inserted + buffers
        if total < 0:
            raise ValueError('Invalid negative duration')
        runtime = plan.get('runtime', {})
        kind = runtime.get('kind', 'none')
        if kind not in {'none', 'hard', 'soft'}:
            raise ValueError('runtime.kind must be none, hard or soft')
        budget = 'not_set'
        if kind != 'none':
            try:
                target = Fraction(str(runtime['target_seconds']))
                tolerance = Fraction(str(runtime.get('tolerance_seconds', 0)))
            except (ValueError, ZeroDivisionError):
                raise ValueError('Runtime values must be finite numbers')
            if target <= 0 or tolerance < 0:
                raise ValueError('Invalid target/tolerance')
            budget = 'over_target' if total > target + tolerance else 'within_upper_target'
        return {'selected_ids': sorted(selected), 'base_seconds': (base_range[1]-base_range[0])/rate,
                'removed_union_frames': merged, 'removed_seconds': removed/rate,
                'inserted_seconds': float(inserted), 'buffer_seconds': float(buffers),
                'fixed_extra_seconds': fixed/rate, 'transition_overlap_seconds': transition/rate,
                'estimated_seconds': float(total), 'exact_seconds_fraction': str(total),
                'budget': budget, 'hard_target_exceeded': kind == 'hard' and budget == 'over_target',
                'issues': problems}
    proposed_report, confirmed_report = calculate(proposed), calculate(confirmed)
    issues = proposed_report['issues'] + confirmed_report['issues']
    if custom:
        issues.append({'ids': custom, 'issue': 'custom_choices_need_revised_ranges_and_confirmation'})
    pending = sorted(proposed - confirmed)
    unresolved = bool(issues or pending or proposed_report['hard_target_exceeded'])
    return {'schema_version': '1.0', 'revision': plan['revision'],
            'status': 'NEEDS_REVIEW' if unresolved else 'CHECKED_NOT_AUTHORIZED',
            'recommendation': proposed_report, 'recorded_apply_choices': confirmed_report,
            'pending_recommended_ids': pending, 'honored_keep_ids': sorted(kept), 'issues': issues,
            'item_sha256': {iid: item_digest(item) for iid, item in items.items()},
            'source_context_sha256': source_context_digest(plan),
            'source_identity_checks': checks, 'review_record_identity_checks': choice_evidence,
            'metadata_timing_decode_verified': False, 'human_approval_authenticity': 'NOT VERIFIED BY THIS CHECKER',
            'approval_generated': False, 'executable': False, 'audio_modified': False,
            '_protected_paths': protected_paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = audit(json.loads(args.plan.read_text(encoding='utf-8')), args.plan.resolve().parent)
        protected = result.pop('_protected_paths')
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.report:
            outside_package(args.report)
            distinct_output(args.report, args.plan, *protected)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf-8') as handle:
                handle.write(text)
        print(text, end='')
        return 2 if result['status'] == 'NEEDS_REVIEW' else 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'INVALID', 'error': str(exc), 'executable': False}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
