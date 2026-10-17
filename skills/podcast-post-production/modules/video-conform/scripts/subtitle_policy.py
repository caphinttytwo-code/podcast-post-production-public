"""Conservative numeric notation and exact, snapshot-bound format exceptions."""
import hashlib
import re
import unicodedata

NUMERIC_STYLES = ('spoken', 'arabic')
# Only a single decimal and an optional percentage/per-mille suffix. Dates,
# signs, ranges, fractions and multi-dot versions need explicit review.
ARABIC = re.compile(r'(?<![\d.．%％‰])\d+(?:[.．]\d+)?[%％‰]?(?![\d.．%％‰])')


def numeric_literals(text, style):
    if style not in NUMERIC_STYLES:
        raise ValueError('unknown numeric style')
    return [m.group() for m in ARABIC.finditer(text)] if style == 'arabic' else []


def mask_literals(text, literals):
    for literal in sorted(literals, key=len, reverse=True):
        if not literal or '\n' in literal or not any(unicodedata.category(c)[0] in 'PS' for c in literal):
            raise ValueError('format literal requires a nonempty single-line symbol-bearing token')
        text = text.replace(literal, '字' * len(literal))
    return text


def format_policy(text, entries):
    return {'srt_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'entries': entries}


def validate_exceptions(text, cues, policy):
    if policy is None:
        return {}
    if policy.get('srt_sha256') != hashlib.sha256(text.encode('utf-8')).hexdigest():
        raise ValueError('format exceptions belong to another SRT snapshot')
    result = {}
    by_number = {c.number: c for c in cues}
    for e in policy.get('entries', []):
        n = e['cue_number']
        if type(n) is not int or n not in by_number or n in result:
            raise ValueError('invalid or duplicate exception cue')
        if e['text'] != '\n'.join(by_number[n].lines) or not isinstance(e.get('approval_basis'), str) or not e['approval_basis'].strip():
            raise ValueError('exception text changed or approval basis missing')
        literals = e['literals']
        if not isinstance(literals, list) or not literals or any(not isinstance(t, str) or not t or t not in e['text'] for t in literals):
            raise ValueError('exception literal is absent')
        mask_literals(e['text'], literals)
        result[n] = literals
    return result
