import json

from state_delta import EffectContract, Rule, Verdict, diff, proof_id, verify
from state_delta.cli import main


def calendar_states():
    before = {
        "event": {
            "id": "e-7",
            "title": "Planning",
            "room": "A",
            "attendees": ["ana", "gio"],
        },
        "permissions": {"guest_can_invite": False},
        "audit": {"updated_by": None},
    }
    after = {
        "event": {
            "id": "e-7",
            "title": "Planning - Q3",
            "room": "A",
            "attendees": ["ana", "gio"],
        },
        "permissions": {"guest_can_invite": False},
        "audit": {"updated_by": "agent-17"},
    }
    return before, after


def test_diff_leaf_paths_are_stable():
    before, after = calendar_states()
    assert [c.path for c in diff(before, after)] == ["/audit/updated_by", "/event/title"]


def test_allowed_change_and_required_postcondition_verify():
    before, after = calendar_states()
    contract = EffectContract(
        allowed=("/event/title", "/audit/updated_by"),
        forbidden=("/permissions/*",),
        required=(
            Rule("equals", "/event/title", "Planning - Q3"),
            Rule("unchanged", "/event/attendees"),
        ),
    )
    report = verify(before, after, contract)
    assert report.verdict is Verdict.VERIFIED
    assert not report.unexpected
    assert not report.forbidden


def test_forbidden_side_effect_fails_even_if_requested_change_succeeds():
    before, after = calendar_states()
    after["permissions"]["guest_can_invite"] = True
    contract = EffectContract(
        allowed=("/event/title", "/audit/updated_by"),
        forbidden=("/permissions/*",),
        required=(Rule("equals", "/event/title", "Planning - Q3"),),
    )
    report = verify(before, after, contract)
    assert report.verdict is Verdict.FAILED
    assert [c.path for c in report.forbidden] == ["/permissions/guest_can_invite"]
    assert [c.path for c in report.unexpected] == ["/permissions/guest_can_invite"]


def test_delta_rule():
    before = {"invoice": {"balance": 100}}
    after = {"invoice": {"balance": 70}}
    contract = EffectContract(
        allowed=("/invoice/balance",),
        required=(Rule("delta", "/invoice/balance", -30),),
    )
    assert verify(before, after, contract).verdict is Verdict.VERIFIED


def test_missing_required_path_fails():
    report = verify({}, {}, EffectContract(required=(Rule("exists", "/receipt/id"),)))
    assert report.verdict is Verdict.FAILED
    assert "missing" in report.rule_results[0].detail


def test_proof_id_is_order_independent_for_json_objects():
    contract = EffectContract(allowed=("/x",))
    first = proof_id({"a": 1, "b": 2}, {"x": 3}, contract)
    second = proof_id({"b": 2, "a": 1}, {"x": 3}, contract)
    assert first == second


def test_cli_returns_failure_and_json(tmp_path, capsys):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    contract = tmp_path / "contract.json"
    before.write_text(json.dumps({"x": 1}), encoding="utf-8")
    after.write_text(json.dumps({"x": 2, "secret": True}), encoding="utf-8")
    contract.write_text(json.dumps({"allowed": ["/x"]}), encoding="utf-8")

    assert main([str(before), str(after), str(contract), "--json"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "FAILED"
    assert output["unexpected"][0]["path"] == "/secret"
