import sys

from PySide6.QtWidgets import QApplication

from launcher import config
from launcher.ui.main_window import LauncherWindow
from launcher.ui.styles import setup_theme


def run_launcher_gui() -> int:
    """Initialize and run the launcher GUI.

    Returns:
        Application exit code.
    """
    print("Initializing GUI components...")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.LAUNCHER_VERSION)
    app.setOrganizationName("Ner-Kun")

    setup_theme(app)

    window = LauncherWindow()
    window.show()

    print("GUI started successfully.")

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_launcher_gui())
