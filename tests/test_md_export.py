from fakehw import branding, cli, i18n
from fakehw.report.json_export import export_json
from fakehw.report.md_export import export_markdown, render_markdown

from test_ui_viewmodel import make_report


def test_markdown_header_uses_branding_and_metadata():
    md = render_markdown(make_report(), lang="en")
    assert md.startswith(f"# {branding.APP_NAME}")
    assert branding.TAGLINE in md
    assert "2026.10.20" in md and "2026.06.26" in md
    assert "2024-01-01" in md


def test_summary_table_has_one_row_per_device():
    md = render_markdown(make_report(), lang="en")
    table = [l for l in md.splitlines() if l.startswith("| ") and "Likely counterfeit" in l or l.startswith("| ") and "Information" in l or l.startswith("| ") and "Could not verify" in l]
    assert len(table) == 5


def test_details_contain_findings_evidence_and_recommendation():
    md = render_markdown(make_report(), lang="en")
    assert "kb.entry_marked_counterfeit" in md
    assert "db_marks_counterfeit=True" in md and "Check origin." in md
    assert "storage.nvme_vid_unregistered" in md  # listed under "could not verify"


def test_disclaimer_present():
    assert i18n.t("disclaimer", lang="en") in render_markdown(make_report(), lang="en")


def test_markdown_escapes_device_strings():
    md = render_markdown(make_report(), lang="en")
    assert "<b>Flash</b>" not in md


def test_pipes_in_names_do_not_break_the_table():
    r = make_report()
    r.devices[0].strings["name"] = "A | B"
    row = next(l for l in render_markdown(r, lang="en").splitlines() if "A \\| B" in l)
    assert row.count("|") - row.count("\\|") == 7  # 6 columns -> 7 separators


def test_russian_report():
    md = render_markdown(make_report(), lang="ru")
    assert "Вероятная подделка" in md and i18n.t("disclaimer", lang="ru") in md
    assert "Likely counterfeit" not in md


def test_render_does_not_leave_language_changed():
    i18n.set_language("en")
    render_markdown(make_report(), lang="ru")
    assert i18n.get_language() == "en"


def test_same_input_same_output():
    assert render_markdown(make_report(), lang="en") == render_markdown(make_report(), lang="en")


def test_no_verdict_word_fake_in_report_text():
    md = render_markdown(make_report(), lang="en").replace("kb.entry_marked_counterfeit", "")
    assert "fake" not in md.lower().replace(branding.APP_NAME.lower(), "")


def test_export_markdown_writes_utf8_file(tmp_path):
    out = tmp_path / "r.md"
    export_markdown(make_report(), out, lang="ru")
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n") and "Устройство" in text


def test_json_and_markdown_share_the_same_report_data(tmp_path):
    export_json(make_report(), tmp_path / "r.json")
    assert (tmp_path / "r.json").read_text(encoding="utf-8").count('"device_index"') >= 2


def test_cli_scan_markdown_format(tmp_path, monkeypatch):
    monkeypatch.setattr("fakehw.cli.collect", lambda collectors: make_report().devices)
    monkeypatch.setattr("fakehw.cli.build_collectors", lambda only, include_serials, enable_spd=False: [])
    out = tmp_path / "r.md"
    assert cli.main(["scan", "--format", "md", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith(f"# {branding.APP_NAME}")
    i18n.set_language("en")
