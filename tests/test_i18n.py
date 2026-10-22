import pytest

from fakehw import i18n
from fakehw.models.finding import Level


def test_default_language_is_english():
    assert i18n.DEFAULT_LANGUAGE == "en"
    assert i18n.get_language() == "en"


def test_switch_language():
    i18n.set_language("ru")
    try:
        assert i18n.t("level.SUSPICIOUS") == "Подозрительно"
    finally:
        i18n.set_language("en")
    assert i18n.t("level.SUSPICIOUS") == "Suspicious"


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        i18n.set_language("xx")


def test_all_keys_present_in_all_languages():
    assert set(i18n.STRINGS["en"]) == set(i18n.STRINGS["ru"])


def test_only_likely_level_mentions_counterfeit():
    for lang in i18n.SUPPORTED_LANGUAGES:
        for level in Level:
            label = i18n.t(f"level.{level.value}", lang=lang).lower()
            assert label
            if level is not Level.LIKELY_FAKE:
                assert "fake" not in label and "подделк" not in label
            assert "fake" not in label  # never use "fake" as a verdict word


def test_spec_labels():
    assert i18n.t("level.INFO", lang="ru") == "Информация"
    assert i18n.t("level.LIKELY_FAKE", lang="ru") == "Вероятная подделка"
    assert i18n.t("level.UNVERIFIED", lang="ru") == "Не удалось проверить"
    assert i18n.t("level.LIKELY_FAKE", lang="en") == "Likely counterfeit"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        i18n.t("nope")
