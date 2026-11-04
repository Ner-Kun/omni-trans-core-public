from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTableWidgetItem
from qfluentwidgets import (
    Dialog,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from ... import settings
from .provider_config import ProviderConfigDialog


class ConnectionsDialog(Dialog):
    def __init__(self, parent=None):
        super().__init__("Connections", "", parent)
        self.setFixedSize(760, 520)
        self.contentLabel.hide()
        self.yesButton.setText("Save")
        self.cancelButton.setText("Close")

        self._connections = [
            dict(connection)
            for connection in settings.current_settings.get("custom_connections", [])
        ]

        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Provider", "Models"])
        self.table.setSelectionBehavior(
            self.table.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.vBoxLayout.insertWidget(1, self.table)

        button_row = QHBoxLayout()
        self.add_button = PrimaryPushButton("Add", self)
        self.edit_button = PushButton("Edit", self)
        self.remove_button = PushButton("Remove", self)
        self.add_button.clicked.connect(self._add_connection)
        self.edit_button.clicked.connect(self._edit_connection)
        self.remove_button.clicked.connect(self._remove_connection)
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch()
        self.vBoxLayout.insertLayout(2, button_row)

        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._connections))
        for row, connection in enumerate(self._connections):
            models = connection.get("configured_models", [])
            self.table.setItem(
                row, 0, QTableWidgetItem(str(connection.get("name", "")))
            )
            self.table.setItem(
                row, 1, QTableWidgetItem(str(connection.get("provider", "")))
            )
            self.table.setItem(row, 2, QTableWidgetItem(str(len(models))))
        self.edit_button.setEnabled(bool(self._connections))
        self.remove_button.setEnabled(bool(self._connections))

    def _current_connection(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._connections):
            return row, self._connections[row]
        return None, None

    def _add_connection(self) -> None:
        dialog = ProviderConfigDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data:
                self._connections.append(data)
                self._refresh_table()

    def _edit_connection(self) -> None:
        row, connection = self._current_connection()
        if connection is None:
            return
        dialog = ProviderConfigDialog(existing_config=connection, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data:
                self._connections[row] = data
                self._refresh_table()

    def _remove_connection(self) -> None:
        row, connection = self._current_connection()
        if connection is None:
            return
        name = connection.get("name", "")
        box = MessageBox("Remove connection", f"Remove '{name}'?", self)
        box.yesButton.setText("Remove")
        box.cancelButton.setText("Cancel")
        if box.exec() == QDialog.DialogCode.Accepted:
            del self._connections[row]
            settings.current_settings.get("active_model_for_connection", {}).pop(
                name, None
            )
            self._refresh_table()

    def accept(self) -> None:
        settings.current_settings["custom_connections"] = self._connections
        settings.save_settings()
        super().accept()
