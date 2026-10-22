import pytest

from fakehw.models.finding import Level
from fakehw.rules import scoring


@pytest.mark.parametrize(
    "score, level",
    [(0.0, Level.INFO), (0.24, Level.INFO), (0.25, Level.SUSPICIOUS), (0.59, Level.SUSPICIOUS),
     (0.6, Level.LIKELY_FAKE), (1.0, Level.LIKELY_FAKE)],
)
def test_level_thresholds(score, level):
    assert scoring.level_for(score) is level


def test_contribution_is_weight_times_confidence():
    assert scoring.contribution(0.5, 0.5) == pytest.approx(0.25)


def test_total_is_sum_capped_at_one():
    assert scoring.total([0.3, 0.35]) == pytest.approx(0.65)
    assert scoring.total([0.7, 0.7]) == 1.0
    assert scoring.total([]) == 0.0


def test_two_weak_signals_outweigh_one_strong_alone():
    # weighted sum, not "worst rule": 0.3 + 0.35 reaches LIKELY_FAKE although each is only SUSPICIOUS
    assert scoring.level_for(0.3) is Level.SUSPICIOUS and scoring.level_for(0.35) is Level.SUSPICIOUS
    assert scoring.level_for(scoring.total([0.3, 0.35])) is Level.LIKELY_FAKE


@pytest.mark.parametrize(
    "virt, factor",
    [("none", 1.0), ("unknown", 1.0), ("ambiguous", 0.8), ("likely", 0.5)],
)
def test_virtualization_confidence(virt, factor):
    assert scoring.confidence_for("cpu", virt) == factor
    assert scoring.confidence_for("gpu", virt) == factor


def test_virtualization_does_not_touch_other_classes():
    for cls in ("usb", "pci", "ram", "storage"):
        assert scoring.confidence_for(cls, "likely") == 1.0


@pytest.mark.parametrize(
    "present, vendor, state",
    [("false", None, "none"), ("true", "Microsoft Hv", "ambiguous"), ("true", "VMwareVMware", "likely"),
     ("true", None, "likely"), ("unknown", None, "unknown")],
)
def test_virtualization_state_from_cpu_record(present, vendor, state):
    from datetime import datetime, timezone

    from fakehw.models.device import DeviceRecord

    rec = DeviceRecord(
        device_class="cpu", source="cpuid", raw_ids={"hypervisor_present": present},
        strings={"hypervisor_vendor": vendor} if vendor else {}, collected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert scoring.virtualization_state([rec]) == state


def test_virtualization_state_without_cpu_record_is_unknown():
    assert scoring.virtualization_state([]) == "unknown"
