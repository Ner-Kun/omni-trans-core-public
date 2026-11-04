from __future__ import annotations

import logging

from PySide6 import QtGui, QtWidgets
from qfluentwidgets import Theme, setTheme

logger = logging.getLogger(__name__)


def _dark_palette() -> QtGui.QPalette:
    palette = QtGui.QPalette()
    window = QtGui.QColor("#1e1e1e")
    base = QtGui.QColor("#252526")
    button = QtGui.QColor("#2d2d30")
    text = QtGui.QColor("#e6e6e6")
    highlight = QtGui.QColor("#0078d4")

    palette.setColor(QtGui.QPalette.ColorRole.Window, window)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, text)
    palette.setColor(QtGui.QPalette.ColorRole.Base, base)
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, button)
    palette.setColor(QtGui.QPalette.ColorRole.Text, text)
    palette.setColor(QtGui.QPalette.ColorRole.Button, button)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, text)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.Text,
        QtGui.QColor("#7a7a7a"),
    )
    return palette


def apply_theme(
    app: QtWidgets.QApplication,
    *,
    theme_name: str = "black",
    extra_qss: str = "",
    dev_mode: bool = False,
) -> None:
    """Apply the Fluent dark theme and a dark palette for Qt widgets."""
    setTheme(Theme.DARK)
    app.setPalette(_dark_palette())
    app.setStyleSheet("")
    logger.debug("Fluent dark theme applied (legacy theme_name=%s).", theme_name)


def detect_best_font() -> str:
    """Detect the best available system font for UI."""
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
