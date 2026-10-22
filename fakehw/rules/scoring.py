"""Scoring: a device level comes from the weighted sum of fired rules, not from the worst rule.

Thresholds and virtualization factors are design decisions of this MVP (see docs/RULES.md).
"""

from ..models.device import DeviceRecord
from ..models.finding import Level

SUSPICIOUS_THRESHOLD = 0.25
LIKELY_THRESHOLD = 0.6

# Hypervisors can present arbitrary CPUID values, so CPU/GPU rules are trusted less in a VM.
# "ambiguous": Hyper-V vendor string, which a Windows host with VBS/Hyper-V (root partition) also shows.
VIRT_FACTORS = {"none": 1.0, "unknown": 1.0, "ambiguous": 0.8, "likely": 0.5}
VIRT_AFFECTED = {"cpu", "gpu"}
HYPERV_VENDOR = "Microsoft Hv"


def level_for(score: float) -> Level:
    if score >= LIKELY_THRESHOLD:
        return Level.LIKELY_FAKE
    if score >= SUSPICIOUS_THRESHOLD:
        return Level.SUSPICIOUS
    return Level.INFO


def contribution(weight: float, confidence: float) -> float:
    return weight * confidence


def total(contributions: list[float]) -> float:
    return min(1.0, sum(contributions))


def confidence_for(device_class, virtualization: str) -> float:
    cls = getattr(device_class, "value", device_class)
    return VIRT_FACTORS.get(virtualization, 1.0) if cls in VIRT_AFFECTED else 1.0


def virtualization_state(devices: list[DeviceRecord]) -> str:
    """none | likely | ambiguous | unknown, from the first CPU record."""
    for d in devices:
        if d.device_class.value != "cpu":
            continue
        present = d.raw_ids.get("hypervisor_present")
        if present == "false":
            return "none"
        if present == "true":
            return "ambiguous" if d.strings.get("hypervisor_vendor") == HYPERV_VENDOR else "likely"
        return "unknown"
    return "unknown"
