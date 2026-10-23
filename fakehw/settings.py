import json
import os
from pathlib import Path

from pydantic import BaseModel

from . import branding, paths
from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"


def default_path() -> Path:
    override = os.environ.get("FAKEHW_CONFIG")
    if override:
        return Path(override)
    portable = paths.portable_data_dir()
    if portable:
        return portable / "settings.json"
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / branding.APP_NAME / "settings.json"


class Settings(BaseModel):
    language: str = DEFAULT_LANGUAGE
    theme: str = DEFAULT_THEME

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or default_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            s = cls.model_validate(data)
        except (OSError, ValueError):
            return cls()
        if s.language not in SUPPORTED_LANGUAGES:
            s.language = DEFAULT_LANGUAGE
        if s.theme not in THEMES:
            s.theme = DEFAULT_THEME
        return s

    @classmethod
    def update(cls, **changes) -> "Settings":
        """Change some fields and save, keeping the rest of the stored settings."""
        s = cls.load().model_copy(update=changes)
        s.save()
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
