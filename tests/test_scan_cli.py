import json
import sys

import pytest

from fakehw import cli
from fakehw.collectors.base import Collector
from fakehw.models.device import DeviceClass, DeviceRecord
from datetime import datetime, timezone


class StubCollector(Collector):
    def collect(self):
        return [
            DeviceRecord(
                device_class=DeviceClass.CPU, source="stub", raw_ids={"family": "6"},
                collected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
        ]


def test_scan_prints_normalised_json(capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_collectors", lambda only, include_serials, enable_spd=False: [StubCollector()])
    assert cli.main(["scan"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["devices"][0]["class"] == "cpu"
    assert data["devices"][0]["raw_ids"] == {"family": "6"}
    assert set(data["kb_versions"]) == {"pci", "usb"}
    assert "findings" in data and "assessments" in data


def test_scan_output_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "build_collectors", lambda only, include_serials, enable_spd=False: [StubCollector()])
    out = tmp_path / "r.json"
    assert cli.main(["scan", "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["devices"]


def test_scan_passes_options(monkeypatch):
    seen = {}

    def fake(only, include_serials, enable_spd=False):
        seen.update(only=only, include_serials=include_serials)
        return []

    monkeypatch.setattr(cli, "build_collectors", fake)
    cli.main(["scan", "--only", "cpu,usb", "--include-serials"])
    assert seen == {"only": ["cpu", "usb"], "include_serials": True}


def test_scan_rejects_unknown_class(capsys):
    assert cli.main(["scan", "--only", "bogus"]) == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_live_scan_cpu_only(capsys):
    assert cli.main(["scan", "--only", "cpu"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["class"] for d in data["devices"]] == ["cpu"]
    assert data["devices"][0]["errors"] == []
