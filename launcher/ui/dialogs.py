import webbrowser

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QSize, Slot

from launcher.ui.widgets import AnimatedIconButton
from launcher.utils.animations import DonateAnimator
from launcher.utils.icon_manager import IconManager



class DonationDialog(QDialog):
    def __init__(self, parent, app_name, launch_count, donate_url):
        super().__init__(parent)
        self.donate_url = donate_url

        self.setObjectName("DonationDialog")

        self.setWindowTitle("Support Development")
        self.setFixedSize(450, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        icon_container = QHBoxLayout()
        icon_container.addStretch()

        self.heart_btn = AnimatedIconButton()
        self.heart_btn.setObjectName("DonateIcon")
        self.heart_btn.setFixedSize(80, 80)
        self.heart_btn.setIconSize(QSize(64, 64))
        self.heart_btn.setIcon(IconManager.get_qicon("donate"))
        self.heart_btn.setCursor(Qt.PointingHandCursor)
        self.heart_btn.clicked.connect(
            self.on_support_clicked
        )

        self.animator = DonateAnimator(self.heart_btn)
        self.animator.selected_type = "heartbeat"
        self.animator.start()

        icon_container.addWidget(self.heart_btn)
        icon_container.addStretch()
        layout.addLayout(icon_container)

        title = QLabel(f"Wow! {launch_count} Launches!")
        title.setObjectName("DonateTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            f"You've used {app_name} {launch_count} times.\n"
            "It's free to use, but its development takes time and effort.\n"
            "Support helps continue its development."
        )
        msg.setObjectName("DonateMessage")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()

        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("LaterBtn")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self.reject)

        self.btn_support = QPushButton("Support")
        self.btn_support.setObjectName("SupportBtn")
        self.btn_support.setCursor(Qt.PointingHandCursor)
        self.btn_support.setFixedSize(140, 40)
        self.btn_support.clicked.connect(self.on_support_clicked)

        btn_layout.addWidget(self.btn_later)
        btn_layout.addWidget(self.btn_support)

        layout.addLayout(btn_layout)

    @Slot()
    def on_support_clicked(self):
        webbrowser.open(self.donate_url)
        self.accept()


class CriticalUpdateDialog(QDialog):
    def __init__(self, parent, app_name, current_ver, new_ver):
        super().__init__(parent)
        self.setObjectName("CriticalUpdateDialog")

        self.setWindowTitle("Critical Update Required")
        self.setFixedSize(450, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        title = QLabel(f"Critical Update for {app_name}")
        title.setObjectName("CriticalTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        msg = QLabel(
            f"You are using version <b>{current_ver}</b>.<br>"
            f"Version <b>{new_ver}</b> contains important fixes.<br><br>"
            "It is highly recommended to update before launching."
        )
        msg.setObjectName("CriticalMessage")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("CriticalCancelBtn")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_launch_anyway = QPushButton("Launch Anyway")
        self.btn_launch_anyway.setObjectName("CriticalLaunchBtn")
        self.btn_launch_anyway.setCursor(Qt.PointingHandCursor)
        self.btn_launch_anyway.clicked.connect(self.on_launch_anyway)

        self.btn_update = QPushButton("Update Now")
        self.btn_update.setObjectName("CriticalUpdateBtn")
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_launch_anyway)
        btn_layout.addWidget(self.btn_update)

        layout.addLayout(btn_layout)

        self.result_action = "cancel"

    @Slot()
    def on_launch_anyway(self):
        self.result_action = "launch"
        super().accept()

    @Slot()
    def accept(self):
        self.result_action = "update"
        super().accept()

    @Slot()
    def reject(self):
        self.result_action = "cancel"
        super().reject()
