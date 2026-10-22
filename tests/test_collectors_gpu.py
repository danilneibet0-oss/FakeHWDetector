import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fakehw.collectors._gpu_io import GpuProbeUnavailable
from fakehw.collectors.gpu import GpuCollector
from fakehw.collectors.pci import PciCollector

FIX = Path(__file__).parent / "fixtures" / "collectors"
T = datetime(2024, 1, 1, tzinfo=timezone.utc)
CLOCK = lambda: T  # noqa: E731


class FakeSource:
    def __init__(self, entries):
        self.entries = entries

    def query(self):
        return self.entries


def pnp():
    return json.loads((FIX / "local_pnp.json").read_text(encoding="utf-8"))["entries"]


def probe_data():
    d = json.loads((FIX / "local_gpu_probe.json").read_text(encoding="utf-8"))
    return copy.deepcopy(d["dxgi"]), copy.deepcopy(d["nvml"])


def collect(probe=None, entries=None):
    probe = probe or (lambda: probe_data())
    return GpuCollector(FakeSource(entries or pnp()), probe=probe, clock=CLOCK).collect()


def test_real_fixture_enriches_the_pci_gpu_record():
    recs = collect()
    assert len(recs) == 1
    r = recs[0]
    assert r.device_class.value == "gpu" and r.source == "wmi:Win32_PnPEntity+dxgi+nvml"
    assert r.raw_ids["vendor_id"] == "10DE" and r.raw_ids["device_id"] == "2486"
    assert r.raw_ids["vram_dedicated_bytes"] == "8413773824"
    assert r.raw_ids["nvml_vram_total_bytes"] == "8589934592"
    assert r.raw_ids["mem_bus_width_bits"] == "256"
    assert r.raw_ids["pcie_gen_current"] == "4" and r.raw_ids["pcie_gen_max"] == "4"
    assert r.raw_ids["pcie_width_current"] == "16" and r.raw_ids["pcie_width_max"] == "16"
    assert r.strings["dxgi_description"] == "NVIDIA GeForce RTX 3060 Ti"
    assert r.strings["nvml_name"] == "NVIDIA GeForce RTX 3060 Ti"
    assert r.errors == []


def test_software_adapter_does_not_create_a_record():
    assert all(r.raw_ids["vendor_id"] != "1414" for r in collect())


def test_no_probe_keeps_pci_record_and_notes_it():
    def none():
        raise GpuProbeUnavailable("no dxgi")

    r = collect(probe=none)[0]
    assert "vram_dedicated_bytes" not in r.raw_ids and "mem_bus_width_bits" not in r.raw_ids
    assert r.raw_ids["vendor_id"] == "10DE"
    assert any("no dxgi" in e for e in r.errors)


def test_dxgi_only_when_nvml_missing():
    def only_dxgi():
        d, _ = probe_data()
        return d, []

    r = collect(probe=only_dxgi)[0]
    assert r.raw_ids["vram_dedicated_bytes"] == "8413773824"
    assert "mem_bus_width_bits" not in r.raw_ids and r.source.endswith("+dxgi")


def test_nvml_entry_for_other_device_is_not_attached():
    def other_nvml():
        d, n = probe_data()
        n[0]["pci_device_id"] = 0x1234_10DE
        return d, n

    assert "mem_bus_width_bits" not in collect(probe=other_nvml)[0].raw_ids


def test_two_identical_gpus_consume_probe_entries_in_order():
    entries = copy.deepcopy(pnp())
    gpu = next(e for e in entries if "VEN_10DE&DEV_2486" in e["DeviceID"])
    twin = copy.deepcopy(gpu)
    twin["DeviceID"] = gpu["DeviceID"].rsplit("\\", 1)[0] + "\\4&FFFFFFFF&0&0010"

    def two():
        d, n = probe_data()
        d.insert(1, copy.deepcopy(d[0]))
        d[1]["dedicated_video_memory"] = 4294967296
        n.append(copy.deepcopy(n[0]))
        n[1]["memory_bus_width"] = 128
        return d, n

    recs = collect(probe=two, entries=entries + [twin])
    assert len(recs) == 2
    assert {r.raw_ids["vram_dedicated_bytes"] for r in recs} == {"8413773824", "4294967296"}
    assert {r.raw_ids["mem_bus_width_bits"] for r in recs} == {"256", "128"}


def test_pci_collector_can_leave_gpus_to_the_gpu_collector():
    with_gpu = PciCollector(FakeSource(pnp()), clock=CLOCK).collect()
    without = PciCollector(FakeSource(pnp()), include_gpu=False, clock=CLOCK).collect()
    assert any(r.device_class.value == "gpu" for r in with_gpu)
    assert not any(r.device_class.value == "gpu" for r in without)
    assert len(without) == len(with_gpu) - 1


def test_deterministic():
    a = [r.model_dump_json() for r in collect()]
    b = [r.model_dump_json() for r in collect()]
    assert a == b


def test_pci_source_failure_is_reported():
    from fakehw.collectors.powershell import PsQueryError

    class Broken:
        def query(self):
            raise PsQueryError("boom")

    recs = GpuCollector(Broken(), probe=probe_data, clock=CLOCK).collect()
    assert len(recs) == 1 and recs[0].errors


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
def test_live_dxgi_has_a_hardware_adapter():
    from fakehw.collectors import _gpu_io

    adapters = _gpu_io.dxgi_adapters()
    assert any(a["vendor_id"] != 0x1414 for a in adapters)  # at least one non-Microsoft (hardware) adapter
