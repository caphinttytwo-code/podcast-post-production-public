#!/usr/bin/env python3
"""Plan an ASR request or append a sanitized actual attempt to its project ledger."""
import argparse
from decimal import InvalidOperation
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.asr_route import append_ledger, ledger_row, plan
from shared.guards import guard_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("plan")
    build.add_argument("spec", type=Path)
    build.add_argument("--output", required=True, type=Path)
    record = actions.add_parser("record")
    record.add_argument("plan", type=Path)
    record.add_argument("attempt", type=Path)
    record.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "plan":
            spec = json.loads(args.spec.read_bytes())
            result = plan(spec, args.spec.resolve().parent)
            output = guard_path(args.output, args.spec, args.spec.resolve().parent / spec["source"])
            with output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(result["status"])
            return 1 if result["status"] == "BLOCKED" else 0
        result = ledger_row(json.loads(args.plan.read_bytes()), json.loads(args.attempt.read_bytes()))
        print(append_ledger(args.project, result, args.plan, args.attempt))
        return 0
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
