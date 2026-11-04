from PySide6 import QtCore, QtGui
from qfluentwidgets import BodyLabel, Dialog, ProgressBar


class ProgressDialog(Dialog):
    cancel_clicked = QtCore.Signal()

    def __init__(self, title: str, label_text: str, parent=None):
        super().__init__(title, "", parent)
        self.setWindowTitle(title)
        self.setFixedSize(480, 260)
        self.setModal(True)
        self.contentLabel.hide()

        self.label = BodyLabel(label_text, self)
        self.label.setWordWrap(True)

        self.progress_bar = ProgressBar(self)
        self.progress_value_label = BodyLabel("", self)
        self.progress_value_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.textLayout.addWidget(self.label)
        self.textLayout.addWidget(self.progress_bar)
        self.textLayout.addWidget(self.progress_value_label)
        self.textLayout.addStretch(1)

        self.yesButton.hide()
        self.cancel_button = self.cancelButton
        self.cancel_button.clicked.disconnect()
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)

        self.buttonLayout.removeWidget(self.yesButton)
        self.buttonLayout.removeWidget(self.cancel_button)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(
            self.cancel_button, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.set_value(0)

    def set_label_text(self, text: str):
        self.label.setText(text)

    def set_button_text(self, text: str):
        self.cancel_button.setText(text)

    def set_maximum(self, value: int):
        self.progress_bar.setMaximum(value)
        self.progress_value_label.setText(f"{self.progress_bar.value()} / {value}")

    def set_value(self, value: int):
        self.progress_bar.setValue(value)
        self.progress_value_label.setText(f"{value} / {self.progress_bar.maximum()}")

    def maximum(self) -> int:
        return self.progress_bar.maximum()

    def reject(self):
        self.cancel_clicked.emit()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.cancel_clicked.emit()
        event.ignore()
