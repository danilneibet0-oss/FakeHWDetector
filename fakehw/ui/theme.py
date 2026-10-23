"""Colour theme: follow Windows, or force light / dark (Qt 6.8+ colour-scheme override)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

_SCHEMES = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}


def apply_theme(theme: str) -> None:
    hints = QGuiApplication.styleHints()
    scheme = _SCHEMES.get(theme)
    if scheme is None:
        hints.unsetColorScheme()  # "system": track the Windows setting again
    else:
        hints.setColorScheme(scheme)
