from PySide6 import QtCore, QtGui, QtWidgets
from qfluentwidgets import BodyLabel, CardWidget, ProgressBar, TableWidget

from ...localization_manager import auto_register, translate


@auto_register(
    ("", "toolTip", "widget.rpm_status.tooltip"),
)
class RPMStatusWidget(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.update_status(
            {
                "message": translate("widget.rpm_status.select_model"),
                "color": "#FFFFFF",
            }
        )

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        self.model_name_label = BodyLabel(self)
        layout.addWidget(self.model_name_label)

        self.stackedWidget = QtWidgets.QStackedWidget(self)
        layout.addWidget(self.stackedWidget)

        self.message_page = QtWidgets.QWidget(self)
        message_layout = QtWidgets.QVBoxLayout(self.message_page)
        message_layout.setContentsMargins(0, 0, 0, 0)
        self.message_label = BodyLabel(self.message_page)
        self.message_label.setWordWrap(True)
        message_layout.addWidget(self.message_label)
        self.stackedWidget.addWidget(self.message_page)

        self.table_page = QtWidgets.QWidget(self)
        table_layout = QtWidgets.QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)
        self.tableWidget = TableWidget(self.table_page)
        self.tableWidget.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tableWidget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.tableWidget.setRowCount(1)
        self.tableWidget.setFixedHeight(80)
        table_layout.addWidget(self.tableWidget)
        self.progressBar = ProgressBar(self.table_page)
        table_layout.addWidget(self.progressBar)
        self.stackedWidget.addWidget(self.table_page)

        self.model_name_label.setText(
            translate("widget.rpm_status.form.model_name_label")
        )

    @QtCore.Slot(dict)
    def update_status(self, data: dict):
        if "connections" in data:
            self._update_multi_connection_status(data["connections"])
            return
        if "message" in data:
            self.message_label.setText(data["message"])
            self.message_label.setStyleSheet(
                f"color: {data.get('color', '#FFFFFF')}; font-weight: bold;"
            )
            self.stackedWidget.setCurrentWidget(self.message_page)

    def _update_multi_connection_status(self, connections_data: list[dict]):
        self.stackedWidget.setCurrentWidget(self.table_page)
        count = len(connections_data)
        self.model_name_label.setText(
            translate("widget.rpm_status.multi_connection", count=count)
        )
        all_limits: dict[str, dict[str, int]] = {}
        for conn_info in connections_data:
            status = conn_info.get("status", {})
            for limit in status.get("limits", []):
                name = limit.get("name", "")
                if not name:
                    continue
                if name not in all_limits:
                    all_limits[name] = {"current": 0, "total": 0}
                all_limits[name]["current"] += limit.get("current", 0)
                all_limits[name]["total"] += limit.get("total", 0)

        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(1)
        if not all_limits:
            return

        limit_names = list(all_limits.keys())
        self.tableWidget.setColumnCount(len(limit_names))
        self.tableWidget.setHorizontalHeaderLabels(limit_names)
        rpm_data = None
        for index, name in enumerate(limit_names):
            info = all_limits[name]
            item = QtWidgets.QTableWidgetItem(
                f"{info['current']} / {info['total']}"
            )
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.tableWidget.setItem(0, index, item)
            if name.upper() == "RPM":
                rpm_data = info

        if rpm_data:
            current = rpm_data.get("current", 0)
            total = rpm_data.get("total", 1)
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(current)
            usage_percent = (current / total) * 100 if total > 0 else 0
            self.progressBar.setFormat(f"{usage_percent:.0f}%")
            if usage_percent > 95:
                color = "#ff5555"
            elif usage_percent > 75:
                color = "#f1fa8c"
            else:
                color = "#50fa7b"
            self.progressBar.setCustomBarColor(QtGui.QColor(color))
        else:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.progressBar.setFormat(translate("widget.rpm_status.rpm_na"))
