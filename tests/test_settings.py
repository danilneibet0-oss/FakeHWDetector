from fakehw.settings import Settings


def test_defaults(tmp_path):
    assert Settings.load(tmp_path / "s.json").language == "en"


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    Settings(language="ru").save(p)
    assert Settings.load(p).language == "ru"


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert Settings.load(p).language == "en"


def test_theme_defaults_to_system_and_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    assert Settings.load(p).theme == "system"
    Settings(theme="dark").save(p)
    assert Settings.load(p).theme == "dark"


def test_unknown_theme_falls_back(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"theme": "purple"}', encoding="utf-8")
    assert Settings.load(p).theme == "system"


def test_update_keeps_other_fields():
    Settings(language="ru", theme="dark").save()
    Settings.update(language="en")
    s = Settings.load()
    assert (s.language, s.theme) == ("en", "dark")


def test_unknown_language_falls_back(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"language": "xx"}', encoding="utf-8")
    assert Settings.load(p).language == "en"
