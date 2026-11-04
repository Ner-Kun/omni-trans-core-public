from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QSize,
    QTimer,
)


class HeartbeatAnimator(QObject):
    """Gently pulses a button icon without repainting the button itself."""

    def __init__(
        self,
        button,
        min_size: QSize,
        max_size: QSize,
        interval_ms: int,
        parent=None,
    ):
        super().__init__(parent or button)
        self.button = button
        self.interval_ms = interval_ms

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._play)

        self.animation = QSequentialAnimationGroup(self)

        up = QPropertyAnimation(button, b"iconSize", self)
        up.setDuration(140)
        up.setStartValue(min_size)
        up.setEndValue(max_size)
        up.setEasingCurve(QEasingCurve.Type.OutQuad)

        down = QPropertyAnimation(button, b"iconSize", self)
        down.setDuration(220)
        down.setStartValue(max_size)
        down.setEndValue(min_size)
        down.setEasingCurve(QEasingCurve.Type.OutBounce)

        self.animation.addAnimation(up)
        self.animation.addAnimation(down)
        self.animation.finished.connect(self._schedule)

    def start(self) -> None:
        self.timer.start(self.interval_ms)

    def stop(self) -> None:
        self.timer.stop()
        self.animation.stop()

    def _play(self) -> None:
        self.animation.start()

    def _schedule(self) -> None:
        self.timer.start(self.interval_ms)
