from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

JSON = Any


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Change:
    path: str
    before: JSON
    after: JSON


@dataclass(frozen=True)
class Rule:
    kind: str
    path: str
    value: JSON = None

    @classmethod
    def from_dict(cls, data: dict[str, JSON]) -> Rule:
        return cls(kind=str(data["kind"]), path=str(data["path"]), value=data.get("value"))


@dataclass(frozen=True)
class EffectContract:
    allowed: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    required: tuple[Rule, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, JSON]) -> EffectContract:
        return cls(
            allowed=tuple(str(x) for x in data.get("allowed", [])),
            forbidden=tuple(str(x) for x in data.get("forbidden", [])),
            required=tuple(Rule.from_dict(x) for x in data.get("required", [])),
        )


@dataclass(frozen=True)
class RuleResult:
    rule: Rule
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerificationReport:
    verdict: Verdict
    proof_id: str
    changes: tuple[Change, ...]
    unexpected: tuple[Change, ...]
    forbidden: tuple[Change, ...]
    rule_results: tuple[RuleResult, ...]

    def to_dict(self) -> dict[str, JSON]:
        return {
            "verdict": self.verdict.value,
            "proof_id": self.proof_id,
            "changes": [change.__dict__ for change in self.changes],
            "unexpected": [change.__dict__ for change in self.unexpected],
            "forbidden": [change.__dict__ for change in self.forbidden],
            "rules": [
                {
                    "kind": result.rule.kind,
                    "path": result.rule.path,
                    "value": result.rule.value,
                    "passed": result.passed,
                    "detail": result.detail,
                }
                for result in self.rule_results
            ],
        }


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def diff(before: JSON, after: JSON, path: str = "") -> list[Change]:
    """Return leaf-level changes using JSON Pointer-like paths."""
    if type(before) is not type(after):
        return [Change(path or "/", before, after)]

    if isinstance(before, dict):
        changes: list[Change] = []
        keys = sorted(set(before) | set(after))
        for key in keys:
            child = f"{path}/{_escape(str(key))}"
            if key not in before:
                changes.append(Change(child, None, after[key]))
            elif key not in after:
                changes.append(Change(child, before[key], None))
            else:
                changes.extend(diff(before[key], after[key], child))
        return changes

    if isinstance(before, list):
        changes = []
        length = max(len(before), len(after))
        for index in range(length):
            child = f"{path}/{index}"
            if index >= len(before):
                changes.append(Change(child, None, after[index]))
            elif index >= len(after):
                changes.append(Change(child, before[index], None))
            else:
                changes.extend(diff(before[index], after[index], child))
        return changes

    if before != after:
        return [Change(path or "/", before, after)]
    return []


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _parts(path: str) -> list[str]:
    if path in {"", "/"}:
        return []
    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in path.lstrip("/").split("/")
    ]


_MISSING = object()


def get_path(document: JSON, path: str) -> JSON:
    current = document
    for part in _parts(path):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


def _check_rule(rule: Rule, before: JSON, after: JSON) -> RuleResult:
    previous = get_path(before, rule.path)
    current = get_path(after, rule.path)

    if rule.kind == "equals":
        passed = current is not _MISSING and current == rule.value
        detail = f"after={current!r}" if current is not _MISSING else "path missing"
        return RuleResult(rule, passed, detail)
    if rule.kind == "exists":
        passed = current is not _MISSING
        return RuleResult(rule, passed, "exists" if passed else "path missing")
    if rule.kind == "not_exists":
        passed = current is _MISSING
        return RuleResult(rule, passed, "absent" if passed else f"after={current!r}")
    if rule.kind == "unchanged":
        passed = previous is not _MISSING and current is not _MISSING and previous == current
        return RuleResult(rule, passed, f"before={previous!r}, after={current!r}")
    if rule.kind == "delta":
        if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
            return RuleResult(rule, False, "delta requires numeric before/after values")
        actual = current - previous
        passed = actual == rule.value
        return RuleResult(rule, passed, f"delta={actual!r}")
    return RuleResult(rule, False, f"unsupported rule kind: {rule.kind}")


def _canonical(value: JSON) -> bytes:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return serialized.encode("utf-8")


def proof_id(before: JSON, after: JSON, contract: EffectContract) -> str:
    payload = {
        "before": before,
        "after": after,
        "contract": {
            "allowed": list(contract.allowed),
            "forbidden": list(contract.forbidden),
            "required": [rule.__dict__ for rule in contract.required],
        },
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def verify(before: JSON, after: JSON, contract: EffectContract) -> VerificationReport:
    changes = tuple(diff(before, after))
    forbidden = tuple(change for change in changes if _matches(change.path, contract.forbidden))
    unexpected = tuple(
        change
        for change in changes
        if contract.allowed and not _matches(change.path, contract.allowed)
    )
    rule_results = tuple(_check_rule(rule, before, after) for rule in contract.required)
    failed = bool(forbidden or unexpected or any(not result.passed for result in rule_results))
    return VerificationReport(
        verdict=Verdict.FAILED if failed else Verdict.VERIFIED,
        proof_id=proof_id(before, after, contract),
        changes=changes,
        unexpected=unexpected,
        forbidden=forbidden,
        rule_results=rule_results,
    )
