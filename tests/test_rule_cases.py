"""Data-driven rule tests: every shipped rule must have positive, negative and borderline cases."""

from pathlib import Path

import pytest
import yaml

from fakehw.kb.updater import KbStore
from fakehw.models.device import DeviceRecord
from fakehw.kb.cpu_tables import CpuTables
from fakehw.kb.gpu_refs import GpuRefs
from fakehw.rules.engine import BUILTIN_RULES_DIR, Engine, EvalContext, RuleState, load_rules

CASES_DIR = Path(__file__).parent / "fixtures" / "cases"
RULES = {r.id: r for r in load_rules()}


def _all_cases():
    out = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        for c in data["cases"]:
            out.append(pytest.param(data["rule"], c, id=f"{data['rule']}::{c['kind']}::{c['name'][:50]}"))
    return out


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    store = KbStore(cache_dir=tmp_path_factory.mktemp("cache"))  # bundled snapshot only
    return EvalContext(pci=store.pci(), usb=store.usb(), cpu_tables=CpuTables.load(), virtualization="none",
                       gpu_refs=GpuRefs.load())


@pytest.mark.parametrize("rule_id, case", _all_cases())
def test_rule_case(ctx, rule_id, case):
    engine = Engine([RULES[rule_id]], ctx)
    device = DeviceRecord.model_validate(case["device"])
    results = engine.evaluate(device)
    assert len(results) == 1, "rule must apply to the device class of the case"
    assert results[0].state is RuleState(case["expect"]), results[0]


def test_every_builtin_rule_has_positive_negative_borderline_cases():
    kinds: dict[str, set[str]] = {}
    for f in CASES_DIR.glob("*.yaml"):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        kinds.setdefault(data["rule"], set()).update(c["kind"] for c in data["cases"])
    assert set(RULES) <= set(kinds), f"rules without any cases: {set(RULES) - set(kinds)}"
    for rule_id in RULES:
        assert {"positive", "negative", "borderline"} <= kinds[rule_id], rule_id


def test_at_least_six_builtin_rules_in_iteration_4():
    assert len(RULES) >= 6
    assert BUILTIN_RULES_DIR.is_dir()
