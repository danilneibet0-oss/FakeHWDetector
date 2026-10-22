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


def test_unknown_language_falls_back(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"language": "xx"}', encoding="utf-8")
    assert Settings.load(p).language == "en"
