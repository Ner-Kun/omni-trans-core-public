from __future__ import annotations

import logging
from pathlib import Path
from PySide6 import QtWidgets, QtGui

logger = logging.getLogger(__name__)

_THEMES_DIR = Path(__file__).parent.parent / "resources"
_cached_stylesheets: dict[str, str] = {}


def get_available_themes() -> list[str]:
    """Return list of available themes from file names.

    Scans the resources directory for theme_*.qss files
    and extracts theme names.

    Returns:
        Sorted list of theme names (e.g., ['black', 'dark', 'white'])
    """
    themes = []
    if not _THEMES_DIR.exists():
        logger.error(f"Themes directory not found: {_THEMES_DIR}")
        return themes

    for f in _THEMES_DIR.glob("theme_*.qss"):
        # theme_black.qss -> black
        name = f.stem.replace("theme_", "")
        themes.append(name)

    return sorted(themes)


def get_theme_stylesheet(theme_name: str = "black") -> str:
    """Return the QSS stylesheet for the specified theme.

    The result is cached after the first call for each theme.

    Args:
        theme_name: Theme name (without 'theme_' prefix and '.qss' suffix)

    Returns:
        Complete QSS stylesheet string, or empty string if theme not found.
    """
    global _cached_stylesheets

    if theme_name in _cached_stylesheets:
        return _cached_stylesheets[theme_name]

    theme_path = _THEMES_DIR / f"theme_{theme_name}.qss"

    if not theme_path.exists():
        logger.error(f"Theme file not found: {theme_path}")
        _cached_stylesheets[theme_name] = ""
        return _cached_stylesheets[theme_name]

    try:
        _cached_stylesheets[theme_name] = theme_path.read_text(encoding="utf-8")
        logger.debug(f"Loaded theme '{theme_name}' from {theme_path}")
    except Exception as e:
        logger.error(f"Failed to read theme file: {e}")
        _cached_stylesheets[theme_name] = ""

    return _cached_stylesheets[theme_name]


def apply_theme(
    app: QtWidgets.QApplication,
    *,
    theme_name: str = "black",
    extra_qss: str = "",
    dev_mode: bool = False
) -> None:
    """Apply the specified theme to a QApplication.

    Args:
        app: The QApplication instance to style.
        theme_name: Name of the theme to apply.
        extra_qss: Optional additional QSS to append after the base theme.
            Use this to override or extend styles for app-specific widgets.
        dev_mode: If True, install style inspector (Ctrl+RightClick to inspect).
    """
    base_qss = get_theme_stylesheet(theme_name)

    if not base_qss:
        logger.warning(f"Theme '{theme_name}' is empty. Application may not be styled.")

    full_qss = base_qss
    if extra_qss:
        full_qss = base_qss + "\n\n/* ---- App-specific overrides ---- */\n" + extra_qss

    app.setStyleSheet(full_qss)
    logger.debug(f"Theme '{theme_name}' applied.")

    # Install style inspector in dev mode
    if dev_mode:
        from .style_inspector import install_style_inspector
        theme_path = str(_THEMES_DIR / f"theme_{theme_name}.qss")
        app._style_inspector = install_style_inspector(app, theme_path)


def detect_best_font() -> str:
    """Detect the best available system font for UI.

    Returns:
        Font family name string.
    """
    available = set(QtGui.QFontDatabase.families())

    candidates = [
        "Segoe UI Variable",
        "Segoe UI",
        "SF Pro Display",
        "SF Pro",
        "Helvetica Neue",
        "Helvetica",
        "Arial",
    ]

    for font in candidates:
        if font in available:
            return font

    return "Arial"
