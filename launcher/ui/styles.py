from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor


def detect_best_font() -> str:
    available = set(QFontDatabase.families())
    for candidate in (
        "Segoe UI Variable",
        "Segoe UI",
        "SF Pro Display",
        "SF Pro",
        "Helvetica Neue",
        "Arial",
    ):
        if candidate in available:
            return candidate
    return "Arial"


def setup_theme(app: QApplication) -> None:
    setTheme(Theme.DARK)
    setThemeColor("#4da6e8")

    font = QFont(detect_best_font(), 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
