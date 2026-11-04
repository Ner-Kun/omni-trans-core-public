from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from omni_trans_core.ui.theme import apply_theme, detect_best_font
from launcher import config


def _load_launcher_styles() -> str:
    """Load launcher-specific QSS overrides from resources."""
    if config.STYLES_QSS.exists():
        with open(config.STYLES_QSS, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def setup_theme(app: QApplication):
    """Apply core dark theme + launcher-specific overrides."""
    best_font = detect_best_font()
    font = QFont(best_font, 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    launcher_qss = _load_launcher_styles()
    apply_theme(app, extra_qss=launcher_qss)
