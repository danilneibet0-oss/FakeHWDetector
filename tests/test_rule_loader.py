from pathlib import Path

import pytest

from fakehw.rules.engine import RuleLoadError, load_rules

VALID = """\
id: pci.dev_not_in_db
applies_to: [gpu, pci]
signals: [device_known]
condition: "not device_known"
weight: 0.4
false_positive_risk: medium
explanation:
  en: Device ID missing from pci.ids.
  ru: ID устройства отсутствует в pci.ids.
recommendation:
  en: Update the database.
  ru: Обновите базу.
"""

PLAIN = """\
id: plain.rule
applies_to: [cpu]
signals: [s]
condition: s
weight: 0.1
false_positive_risk: low
explanation: Plain text
recommendation: Do nothing
"""


def write(d: Path, name: str, text: str):
    (d / name).write_text(text, encoding="utf-8")


def test_loads_valid(tmp_path):
    write(tmp_path, "a.yaml", VALID)
    rules = load_rules(tmp_path)
    assert [r.id for r in rules] == ["pci.dev_not_in_db"]
    assert rules[0].explanation.get("ru").startswith("ID")
    assert rules[0].explanation.get("de").startswith("Device")  # falls back to en


def test_plain_string_text_is_english(tmp_path):
    write(tmp_path, "a.yaml", PLAIN)
    assert load_rules(tmp_path)[0].explanation.get("en") == "Plain text"


def test_empty_dir(tmp_path):
    assert load_rules(tmp_path) == []


def test_missing_dir(tmp_path):
    with pytest.raises(RuleLoadError):
        load_rules(tmp_path / "nope")


def test_broken_yaml(tmp_path):
    write(tmp_path, "a.yaml", "id: [unclosed")
    with pytest.raises(RuleLoadError, match="a.yaml"):
        load_rules(tmp_path)


def test_unknown_field_rejected(tmp_path):
    write(tmp_path, "a.yaml", VALID + "bogus: 1\n")
    with pytest.raises(RuleLoadError):
        load_rules(tmp_path)


def test_duplicate_ids(tmp_path):
    write(tmp_path, "a.yaml", VALID)
    write(tmp_path, "b.yaml", VALID)
    with pytest.raises(RuleLoadError, match="duplicate"):
        load_rules(tmp_path)


def test_bad_condition_rejected(tmp_path):
    write(tmp_path, "a.yaml", VALID.replace('"not device_known"', '"open(1)"'))
    with pytest.raises(RuleLoadError):
        load_rules(tmp_path)


def test_condition_uses_undeclared_signal(tmp_path):
    write(tmp_path, "a.yaml", VALID.replace('"not device_known"', '"other"'))
    with pytest.raises(RuleLoadError, match="undeclared"):
        load_rules(tmp_path)


def test_weight_out_of_range(tmp_path):
    write(tmp_path, "a.yaml", VALID.replace("weight: 0.4", "weight: 2"))
    with pytest.raises(RuleLoadError):
        load_rules(tmp_path)


def test_load_order_is_sorted(tmp_path):
    write(tmp_path, "b.yaml", VALID.replace("pci.dev_not_in_db", "z.rule"))
    write(tmp_path, "a.yaml", VALID)
    assert [r.id for r in load_rules(tmp_path)] == ["pci.dev_not_in_db", "z.rule"]


def test_builtin_rules_dir_loads():
    assert isinstance(load_rules(), list)
