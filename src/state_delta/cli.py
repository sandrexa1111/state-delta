from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import EffectContract, Verdict, verify


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="state-delta",
        description="Verify observable state changes against an explicit contract.",
    )
    parser.add_argument("before", help="JSON state before the operation")
    parser.add_argument("after", help="JSON state after the operation")
    parser.add_argument("contract", help="JSON effect contract")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    contract = EffectContract.from_dict(_load(args.contract))
    report = verify(_load(args.before), _load(args.after), contract)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"VERDICT: {report.verdict.value}")
        print(f"proof_id: {report.proof_id[:16]}")
        print(f"changes: {len(report.changes)}")
        for change in report.unexpected:
            print(f"UNEXPECTED  {change.path}: {change.before!r} -> {change.after!r}")
        for change in report.forbidden:
            print(f"FORBIDDEN   {change.path}: {change.before!r} -> {change.after!r}")
        for result in report.rule_results:
            state = "PASS" if result.passed else "FAIL"
            print(f"{state:4} {result.rule.kind:10} {result.rule.path} ({result.detail})")

    return 0 if report.verdict is Verdict.VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())
