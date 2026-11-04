import ctypes
import subprocess
import sys
from ctypes import wintypes

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

_CONSOLE_CLASSES = {
    "ConsoleWindowClass",
    "PseudoConsoleWindow",
    "CASCADIA_HOSTING_WINDOW_CLASS",
}

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    def _visible_windows() -> list[tuple[int, str, str]]:
        windows: list[tuple[int, str, str]] = []

        def callback(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True

            length = _user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            title_buffer = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, title_buffer, length + 1)

            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            class_buffer = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, class_buffer, 256)

            windows.append((pid.value, title_buffer.value, class_buffer.value))
            return True

        _user32.EnumWindows(_EnumWindowsProc(callback), 0)
        return windows

else:
    def _visible_windows() -> list[tuple[int, str, str]]:
        return []


class AppWindowWatcher(QObject):
    """Wait until the launched app owns a visible GUI window."""

    window_ready = Signal()
    timed_out = Signal()
    process_exited = Signal()

    def __init__(
        self,
        process: subprocess.Popen,
        timeout_ms: int = 30000,
        parent=None,
    ):
        super().__init__(parent)
        self.process = process
        self.timeout_ms = timeout_ms
        self.elapsed_ms = 0

        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._check)

    def start(self) -> None:
        if sys.platform != "win32":
            self.timer.setInterval(1500)
        self.timer.start()

    def _check(self) -> None:
        if self.process.poll() is not None:
            self.timer.stop()
            self.process_exited.emit()
            return

        if self._has_window():
            self.timer.stop()
            self.window_ready.emit()
            return

        self.elapsed_ms += self.timer.interval()
        if self.elapsed_ms >= self.timeout_ms:
            self.timer.stop()
            self.timed_out.emit()

    def _has_window(self) -> bool:
        if sys.platform != "win32":
            return True

        pids = self._process_pids()
        for pid, _title, class_name in _visible_windows():
            if pid not in pids:
                continue
            if class_name in _CONSOLE_CLASSES:
                continue
            return True

        return False

    def _process_pids(self) -> set[int]:
        pids = {self.process.pid}
        try:
            parent = psutil.Process(self.process.pid)
            pids.update(child.pid for child in parent.children(recursive=True))
        except psutil.Error:
            pass
        return pids
