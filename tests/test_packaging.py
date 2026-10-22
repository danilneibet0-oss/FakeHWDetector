import subprocess
import sys
from pathlib import Path

import pytest

from fakehw import branding, cli

ROOT = Path(__file__).resolve().parent.parent


def test_module_entry_point_runs(capsys):
    r = subprocess.run([sys.executable, "-m", "fakehw", "--version"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and branding.APP_NAME in r.stdout


def test_selftest_checks_bundled_resources(capsys):
    assert cli.main(["selftest"]) == 0
    out = capsys.readouterr().out
    for item in ("rules", "pci.ids", "usb.ids", "cpu_arch", "gpu_refs"):
        assert item in out
    assert "FAIL" not in out


def test_selftest_reports_failure(monkeypatch, capsys):
    from fakehw import selftest

    monkeypatch.setattr(selftest, "CHECKS", [("broken", lambda: (_ for _ in ()).throw(RuntimeError("missing file")))])
    assert selftest.run() == 1
    assert "FAIL" in capsys.readouterr().out


def test_build_script_bundles_every_data_directory():
    text = (ROOT / "tools" / "build_exe.py").read_text(encoding="utf-8")
    for needle in ("fakehw/kb/data", "fakehw/rules/rules", "branding"):
        assert needle in text


def build_exe():
    sys.path.insert(0, str(ROOT / "tools"))
    import build_exe as module

    return module


def test_portable_zip_contains_folder_and_marker(tmp_path):
    import zipfile

    from fakehw.paths import PORTABLE_MARKER

    folder = tmp_path / "fakehw"
    (folder / "_internal").mkdir(parents=True)
    (folder / f"{branding.APP_NAME}.exe").write_bytes(b"MZ")
    (folder / "_internal" / "lib.dll").write_bytes(b"x")
    out = build_exe().write_portable_zip(folder, tmp_path / "out" / "p.zip")
    names = zipfile.ZipFile(out).namelist()
    root = branding.APP_NAME
    assert sorted(names) == sorted([f"{root}/{branding.APP_NAME}.exe", f"{root}/_internal/lib.dll", f"{root}/{PORTABLE_MARKER}"])
    assert not (folder / PORTABLE_MARKER).exists()  # the marker never lands in the folder the installer packs


def test_installer_gets_names_from_branding():
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "FakeHWDetector" not in iss and "{#AppName}" in iss
    assert "PrivilegesRequired=lowest" in iss and "Russian.isl" in iss
    cmd = build_exe().iscc_command("ISCC.exe", ROOT / "dist" / "fakehw", ROOT / "dist")
    assert f"/DAppName={branding.APP_NAME}" in cmd and f"/DTagline={branding.TAGLINE}" in cmd
    assert any(a.startswith("/DOutputName=") and a.endswith("-setup") for a in cmd)


@pytest.mark.parametrize("name", ["README.md", "README.ru.md"])
def test_readme_is_rendered_from_branding_templates(name):
    sys.path.insert(0, str(ROOT / "tools"))
    import render_readme

    assert (ROOT / name).read_text(encoding="utf-8") == render_readme.render(name)


def test_readme_documents_limits_and_comparison():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    ru = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    for text in (en, ru):
        assert branding.APP_NAME in text and branding.TAGLINE in text
        assert "GPU-Z" in text and "HWiNFO" in text
    assert "False alarms" in en and "Limitations" in en
    assert "Ложные срабатывания" in ru and "Ограничения" in ru


def test_readme_has_no_hardcoded_product_name_outside_branding_values():
    # templates hold ${APP_NAME}; the rendered file must equal the render (checked above), so names cannot drift
    for tmpl in (ROOT / "docs" / "readme").glob("*.tmpl"):
        assert "FakeHWDetector" not in tmpl.read_text(encoding="utf-8")
