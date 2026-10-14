#!/usr/bin/env python3
"""Check task-specific local dependencies; never install or call model services."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.environment import inspect, FEATURES
from shared.files import outside_package, distinct_output
from shared.project_index import MODES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=MODES, required=True)
    parser.add_argument('--require-review', action='store_true')
    parser.add_argument('--feature', choices=sorted({x for values in FEATURES.values() for x in values}), default='full')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--font', type=Path)
    parser.add_argument('--text', default='合成测试\n技术验收 Audio 12')
    parser.add_argument('--smoke-dir', type=Path, help='Fresh project directory for synthetic smoke outputs')
    parser.add_argument('--output-dir', type=Path, help='Check intended project output parent without creating it')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--allow-review-legacy', action='store_true', help='Explicit older build for --feature review only; smoke verification required')
    args = parser.parse_args()
    if args.allow_review_legacy and (args.feature != 'review' or not args.smoke_dir):
        parser.error('--allow-review-legacy requires --feature review and --smoke-dir')
    if args.report:
        outside_package(args.report)
        distinct_output(args.report, *[x for x in (args.font, Path(__file__), Path(args.ffmpeg), Path(args.ffprobe)) if x])
        if args.report.exists():
            raise FileExistsError('Use a fresh environment report path')
        if args.smoke_dir and args.report.resolve() == args.smoke_dir.resolve():
            raise ValueError('Report and smoke directory must be distinct')
    if args.smoke_dir:
        outside_package(args.smoke_dir)
        if args.smoke_dir.exists():
            raise FileExistsError('Use a fresh smoke directory')
    result = inspect(args.mode, args.require_review, feature=args.feature,
                     ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, font=args.font, text=args.text,
                     smoke_dir=args.smoke_dir, output_dir=args.output_dir,
                     allow_review_legacy=args.allow_review_legacy)
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(content, encoding='utf-8')
    print(content, end='')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
