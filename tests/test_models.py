from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from fakehw.models.device import DeviceClass, DeviceRecord
from fakehw.models.finding import Finding, Level
from fakehw.models.report import Report

T = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_device(**kw):
    base = dict(
        device_class=DeviceClass.GPU,
        source="test",
        raw_ids={"vendor": "10DE"},
        strings={"name": "X"},
        collected_at=T,
    )
    base.update(kw)
    return DeviceRecord(**base)


def test_device_defaults():
    d = make_device()
    assert d.privilege_needed is False
    assert d.errors == []


def test_device_class_alias_in_json():
    data = make_device().model_dump(mode="json", by_alias=True)
    assert data["class"] == "gpu"


def test_device_accepts_class_key():
    d = DeviceRecord.model_validate(
        {"class": "cpu", "source": "s", "collected_at": T.isoformat()}
    )
    assert d.device_class is DeviceClass.CPU


def test_device_requires_source():
    with pytest.raises(ValidationError):
        DeviceRecord(device_class="gpu", collected_at=T)  # type: ignore[call-arg]


def test_finding_score_bounds():
    with pytest.raises(ValidationError):
        Finding(rule_id="r", level=Level.INFO, score=1.5, explanation="e")
    with pytest.raises(ValidationError):
        Finding(rule_id="r", level=Level.INFO, score=-0.1, explanation="e")


def test_levels_match_spec():
    assert [l.value for l in Level] == ["INFO", "SUSPICIOUS", "LIKELY_FAKE", "UNVERIFIED"]


def test_report_json_is_deterministic():
    d = make_device()
    r1 = Report(devices=[d], findings=[], generated_at=T, kb_versions={"pci": "1"})
    r2 = Report(devices=[d], findings=[], generated_at=T, kb_versions={"pci": "1"})
    assert r1.to_json() == r2.to_json()
