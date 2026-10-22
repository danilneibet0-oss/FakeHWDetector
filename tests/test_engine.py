import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakehw import i18n
from fakehw.collectors.cpu import CpuCollector
from fakehw.collectors.gpu import GpuCollector
from fakehw.collectors.memory import MemoryCollector
from fakehw.collectors.pci import PciCollector
from fakehw.collectors.storage import StorageCollector
from fakehw.collectors.usb import UsbCollector
from fakehw.kb.updater import KbStore
from fakehw.models.device import DeviceClass, DeviceRecord
from fakehw.models.finding import Level
from fakehw.kb.cpu_tables import CpuTables
from fakehw.kb.gpu_refs import GpuRefs
from fakehw.rules.engine import Engine, EvalContext, Rule, RuleState, load_rules

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)


def dev(cls="usb", **raw):
    return DeviceRecord(device_class=cls, source="t", raw_ids=raw, collected_at=T)


def rule(rid, applies="usb", signals=("a",), cond="a", weight=0.3, risk="medium"):
    return Rule.model_validate({
        "id": rid, "applies_to": [applies] if isinstance(applies, str) else list(applies),
        "signals": list(signals), "condition": cond, "weight": weight, "false_positive_risk": risk,
        "explanation": {"en": f"{rid} fired.", "ru": f"{rid} сработало."},
        "recommendation": {"en": "Check it.", "ru": "Проверьте."},
    })


def provider(values):
    return lambda device, ctx: dict(values)


@pytest.fixture
def ctx():
    return EvalContext(pci=None, usb=None, cpu_tables=None, virtualization="none")


def test_fired_rule_produces_finding_with_basis_and_disclaimer(ctx):
    eng = Engine([rule("r1")], ctx, signal_provider=provider({"a": True}))
    findings, assessments = eng.run([dev()])
    f = findings[0]
    assert f.rule_id == "r1" and f.device_index == 0
    assert f.score == pytest.approx(0.3) and f.level is Level.SUSPICIOUS
    assert "a=True" in f.explanation  # states the signals the verdict rests on
    assert i18n.t("disclaimer", lang="en") in f.explanation
    assert f.recommendation == "Check it."
    assert assessments[0].level is Level.SUSPICIOUS


def test_language_selects_texts(ctx):
    eng = Engine([rule("r1")], ctx, lang="ru", signal_provider=provider({"a": True}))
    f = eng.run([dev()])[0][0]
    assert f.explanation.startswith("r1 сработало.")
    assert i18n.t("disclaimer", lang="ru") in f.explanation
    assert f.recommendation == "Проверьте."


def test_not_applicable_class_is_skipped(ctx):
    eng = Engine([rule("r1", applies="cpu")], ctx, signal_provider=provider({"a": True}))
    assert eng.evaluate(dev("usb")) == []


def test_unknown_signal_gives_unverified_not_guess(ctx):
    eng = Engine([rule("r1")], ctx, signal_provider=provider({"a": None}))
    res = eng.evaluate(dev())[0]
    assert res.state is RuleState.UNVERIFIED and res.missing == ["a"]
    findings, assessments = eng.run([dev()])
    assert findings[0].level is Level.UNVERIFIED and findings[0].score == 0
    assert assessments[0].level is Level.UNVERIFIED


def test_not_fired_device_is_info_when_something_was_checked(ctx):
    eng = Engine([rule("r1"), rule("r2", signals=("b",), cond="b")], ctx,
                 signal_provider=provider({"a": False, "b": None}))
    findings, assessments = eng.run([dev()])
    assert assessments[0].level is Level.INFO
    assert [f.level for f in findings] == [Level.UNVERIFIED]


def test_weighted_sum_not_worst_rule(ctx):
    rules = [rule("r1", weight=0.3), rule("r2", weight=0.35)]
    eng = Engine(rules, ctx, signal_provider=provider({"a": True}))
    findings, assessments = eng.run([dev()])
    assert {f.level for f in findings} == {Level.SUSPICIOUS}
    assert assessments[0].score == pytest.approx(0.65)
    assert assessments[0].level is Level.LIKELY_FAKE


def test_virtualization_lowers_cpu_and_gpu_confidence_only():
    ctx = EvalContext(pci=None, usb=None, cpu_tables=None, virtualization="likely")
    rules = [rule("rc", applies="cpu", weight=0.6), rule("ru", applies="usb", weight=0.6)]
    eng = Engine(rules, ctx, signal_provider=provider({"a": True}))
    cpu = eng.run([dev("cpu")])
    usb = eng.run([dev("usb")])
    assert cpu[0][0].score == pytest.approx(0.3) and cpu[1][0].level is Level.SUSPICIOUS
    assert usb[0][0].score == pytest.approx(0.6) and usb[1][0].level is Level.LIKELY_FAKE
    assert any("irtualiz" in e for e in cpu[0][0].evidence)


def test_run_is_deterministic(ctx):
    eng = Engine([rule("r1"), rule("r2")], ctx, signal_provider=provider({"a": True}))
    devices = [dev(), dev()]
    a = eng.run(devices)
    b = eng.run(devices)
    assert [f.model_dump() for f in a[0]] == [f.model_dump() for f in b[0]]
    assert [x.model_dump() for x in a[1]] == [x.model_dump() for x in b[1]]
    assert [f.device_index for f in a[0]] == [0, 0, 1, 1]


def test_assessment_per_device_even_without_rules(ctx):
    eng = Engine([], ctx, signal_provider=provider({}))
    _, assessments = eng.run([dev(), dev()])
    assert [a.device_index for a in assessments] == [0, 1]
    assert all(a.level is Level.UNVERIFIED for a in assessments)  # nothing could be checked


# ---- MVP criterion: no LIKELY_FAKE on the developer's real machine ----

class FakeSource:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def test_no_likely_fake_on_real_machine_fixtures(tmp_path):
    entries = json.loads((FIX / "local_pnp.json").read_text(encoding="utf-8"))["entries"]
    leaves = json.loads((FIX / "local_cpuid.json").read_text(encoding="utf-8"))["leaves"]
    probe = json.loads((FIX / "local_gpu_probe.json").read_text(encoding="utf-8"))
    mem = json.loads((FIX / "local_memory.json").read_text(encoding="utf-8"))["entries"]
    disks = json.loads((FIX / "local_storage.json").read_text(encoding="utf-8"))["entries"]
    nvme_hex = json.loads((FIX / "local_nvme_identify.json").read_text(encoding="utf-8"))["identify"]

    def nvme_only(entry):
        from fakehw.collectors import _storage_io as io

        if entry["BusType"] == "NVMe":
            return {"source": "nvme", **io.parse_nvme_identify(bytes.fromhex(nvme_hex[str(entry["Index"])]))}
        raise io.PrivilegeRequired("denied")

    clock = lambda: T  # noqa: E731
    devices = (
        PciCollector(FakeSource(entries), include_gpu=False, clock=clock).collect()
        + GpuCollector(FakeSource(entries), probe=lambda: (probe["dxgi"], probe["nvml"]), clock=clock).collect()
        + UsbCollector(FakeSource(entries), clock=clock).collect()
        + CpuCollector(leaves_source=lambda: leaves, clock=clock).collect()
        + MemoryCollector(FakeSource(mem), clock=clock).collect()
        + StorageCollector(FakeSource(disks), identify_reader=nvme_only, clock=clock).collect()
    )
    store = KbStore(cache_dir=tmp_path)
    from fakehw.rules.scoring import virtualization_state

    ctx = EvalContext(pci=store.pci(), usb=store.usb(), cpu_tables=CpuTables.load(), gpu_refs=GpuRefs.load(),
                      virtualization=virtualization_state(devices))
    assert ctx.virtualization == "ambiguous"  # Hyper-V root partition on the dev machine
    findings, assessments = Engine(load_rules(), ctx).run(devices)
    assert len(assessments) == len(devices)
    assert not [a for a in assessments if a.level is Level.LIKELY_FAKE]
    assert not [f for f in findings if f.level is Level.LIKELY_FAKE]
    cpu_idx = next(i for i, d in enumerate(devices) if d.device_class is DeviceClass.CPU)
    assert next(a for a in assessments if a.device_index == cpu_idx).level is Level.INFO
    gpu_idx = next(i for i, d in enumerate(devices) if d.device_class is DeviceClass.GPU)
    gpu_findings = [f for f in findings if f.device_index == gpu_idx]
    assert not [f for f in gpu_findings if f.level is not Level.UNVERIFIED]  # nothing fires on the real card
    assert next(a for a in assessments if a.device_index == gpu_idx).level is Level.INFO


def test_report_with_assessments_is_deterministic(ctx):
    from fakehw.models.report import Report

    eng = Engine([rule("r1")], ctx, signal_provider=provider({"a": True}))
    f, a = eng.run([dev()])
    r1 = Report(generated_at=T, devices=[dev()], findings=f, assessments=a).to_json()
    r2 = Report(generated_at=T, devices=[dev()], findings=f, assessments=a).to_json()
    assert r1 == r2 and "assessments" in r1
