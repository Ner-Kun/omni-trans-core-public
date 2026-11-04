import sys
from PySide6.QtWidgets import QApplication
from launcher.ui.main_window import MainWindow
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

    setup_theme(app)

    window = MainWindow()
    window.show()

    print("GUI started successfully.")

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_launcher_gui())
