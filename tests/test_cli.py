import pytest

from fakehw import __version__, branding, i18n
from fakehw.cli import main


@pytest.fixture(autouse=True)
def _reset_lang():
    yield
    i18n.set_language("en")


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert branding.APP_NAME in out and __version__ in out


def test_help_uses_branding(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert branding.CLI_NAME in out and branding.TAGLINE in out


def test_rules_list(capsys, tmp_path):
    (tmp_path / "ok.yaml").write_text(
        "id: t.r\napplies_to: [cpu]\nsignals: [s]\ncondition: s\nweight: 0.1\n"
        "false_positive_risk: low\nexplanation: e\nrecommendation: r\n",
        encoding="utf-8",
    )
    assert main(["rules", "--dir", str(tmp_path)]) == 0
    assert "t.r" in capsys.readouterr().out


def test_rules_bad_dir(tmp_path):
    assert main(["rules", "--dir", str(tmp_path / "nope")]) == 1


def test_config_language_persists(capsys):
    assert main(["config", "--language", "ru"]) == 0
    assert capsys.readouterr().out.strip() == "Язык установлен: ru"  # placeholder filled, not printed as {...}
    i18n.set_language("en")
    assert main(["scan", "--only", "bogus"]) == 2  # picks saved language
    assert "неизвестные" in capsys.readouterr().err.lower()
