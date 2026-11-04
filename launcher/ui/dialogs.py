import webbrowser

from PySide6.QtCore import QSize, Qt, Slot
from qfluentwidgets import Dialog, FluentIcon, PushButton, TransparentToolButton

from launcher.utils.heartbeat import HeartbeatAnimator
from launcher.utils.icon_manager import IconManager


class DonationDialog(Dialog):
    def __init__(self, parent, app_name, launch_count, donate_url):
        super().__init__("Support development", "", parent)
        self.setFixedSize(440, 380)
        self.donate_url = donate_url

        self.titleLabel.setText(f"Wow! {launch_count} launches!")
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.contentLabel.setText(
            f"You've used {app_name} {launch_count} times.\n\n"
            "It's free to use, but development takes time and effort.\n\n"
            "Support helps keep it going."
        )
        self.contentLabel.setWordWrap(True)
        self.contentLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.contentLabel.setFixedWidth(392)

        heart = TransparentToolButton(self)
        donate_icon = IconManager.get_qicon("donate")
        heart.setIcon(
            donate_icon if not donate_icon.isNull() else FluentIcon.HEART.icon()
        )
        heart.setIconSize(QSize(48, 48))
        heart.setFixedSize(64, 64)
        heart.setStyleSheet("background: transparent; border: none;")
        heart.clicked.connect(self._open_donate)
        self.textLayout.insertWidget(0, heart, 0, Qt.AlignmentFlag.AlignHCenter)

        self.heart = heart
        self.heart_animator = HeartbeatAnimator(
            heart,
            QSize(48, 48),
            QSize(56, 56),
            1500,
            self,
        )
        self.heart_animator.start()

        self.yesButton.setText("Support")
        self.cancelButton.setText("Later")
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._open_donate)

    @Slot()
    def _open_donate(self):
        webbrowser.open(self.donate_url)
        self.accept()

    def closeEvent(self, event):
        self.heart_animator.stop()
        super().closeEvent(event)


class CriticalUpdateDialog(Dialog):
    def __init__(self, parent, app_name, current_ver, new_ver):
        super().__init__("Critical update", "", parent)
        self.result_action = "cancel"

        self.titleLabel.setText(f"Critical update for {app_name}")
        self.contentLabel.setText(
            f"You are using <b>{current_ver}</b>.<br>"
            f"Version <b>{new_ver}</b> contains important fixes.<br><br>"
            "It is highly recommended to update before launching."
        )
        self.contentLabel.setWordWrap(True)

        self.cancel_btn = PushButton("Cancel", self)
        self.buttonLayout.insertWidget(0, self.cancel_btn)

        self.yesButton.setText("Update now")
        self.cancelButton.setText("Launch anyway")

        self.yesButton.clicked.disconnect()
        self.cancelButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._choose_update)
        self.cancelButton.clicked.connect(self._choose_launch)
        self.cancel_btn.clicked.connect(self._choose_cancel)

    @Slot()
    def _choose_update(self):
        self.result_action = "update"
        self.accept()

    @Slot()
    def _choose_launch(self):
        self.result_action = "launch"
        self.accept()

    @Slot()
    def _choose_cancel(self):
        self.result_action = "cancel"
        self.reject()
