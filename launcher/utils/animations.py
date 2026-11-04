import random
from PySide6.QtCore import (
    QObject,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QSequentialAnimationGroup,
)
from launcher import config
from rich.console import Console

console = Console()


class DonateAnimator(QObject):
    def __init__(self, button_widget):
        super().__init__()
        self.btn = button_widget
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.play_random_animation)

        self.current_animation = None
        self.animation_types = ["heartbeat", "shake", "spin", "jump"]

        self.selected_type = random.choice(self.animation_types)
        console.log(f"Anim: {self.selected_type}")

    def start(self):
        QTimer.singleShot(2000, self.play_random_animation)

    def play_random_animation(self):
        if self.selected_type == "heartbeat":
            self._anim_heartbeat()
        elif self.selected_type == "shake":
            self._anim_shake()
        elif self.selected_type == "spin":
            self._anim_spin()
        elif self.selected_type == "jump":
            self._anim_jump()

    def _on_finished(self):
        self.timer.start(config.ANIMATION_PAUSE_MS)


    def _anim_heartbeat(self):
        anim = QSequentialAnimationGroup(self)

        a1 = QPropertyAnimation(self.btn, b"p_icon_scale")
        a1.setDuration(150)
        a1.setStartValue(1.0)
        a1.setEndValue(1.2)
        a1.setEasingCurve(QEasingCurve.OutQuad)

        a2 = QPropertyAnimation(self.btn, b"p_icon_scale")
        a2.setDuration(150)
        a2.setEndValue(0.9)

        a3 = QPropertyAnimation(self.btn, b"p_icon_scale")
        a3.setDuration(150)
        a3.setEndValue(1.2)

        a4 = QPropertyAnimation(self.btn, b"p_icon_scale")
        a4.setDuration(200)
        a4.setEndValue(1.0)
        a4.setEasingCurve(QEasingCurve.OutBounce)

        anim.addAnimation(a1)
        anim.addAnimation(a2)
        anim.addAnimation(a3)
        anim.addAnimation(a4)

        anim.finished.connect(self._on_finished)
        self.current_animation = anim
        anim.start()

    def _anim_shake(self):
        anim = QSequentialAnimationGroup(self)

        values = [0, -15, 15, -10, 10, -5, 5, 0]
        step = 50

        for val in values:
            a = QPropertyAnimation(self.btn, b"p_icon_rotation")
            a.setDuration(step)
            a.setEndValue(val)
            anim.addAnimation(a)

        anim.finished.connect(self._on_finished)
        self.current_animation = anim
        anim.start()

    def _anim_spin(self):
        anim = QPropertyAnimation(self.btn, b"p_icon_rotation")
        anim.setDuration(800)
        anim.setStartValue(0)
        anim.setEndValue(360)
        anim.setEasingCurve(
            QEasingCurve.InOutBack
        )

        anim.finished.connect(self._on_finished)
        anim.finished.connect(lambda: self.btn.set_icon_rotation(0))

        self.current_animation = anim
        anim.start()

    def _anim_jump(self):
        anim = QSequentialAnimationGroup(self)

        up = QPropertyAnimation(self.btn, b"p_y_offset")
        up.setDuration(300)
        up.setStartValue(0)
        up.setEndValue(-10)
        up.setEasingCurve(QEasingCurve.OutQuad)

        down = QPropertyAnimation(self.btn, b"p_y_offset")
        down.setDuration(600)
        down.setStartValue(-10)
        down.setEndValue(0)
        down.setEasingCurve(QEasingCurve.OutBounce)

        anim.addAnimation(up)
        anim.addAnimation(down)

        anim.finished.connect(self._on_finished)
        self.current_animation = anim
        anim.start()
