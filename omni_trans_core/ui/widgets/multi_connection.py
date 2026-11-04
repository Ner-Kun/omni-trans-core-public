from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    PushButton,
    SmoothScrollArea,
    StrongBodyLabel,
)

from ... import settings
from ...localization_manager import auto_register
from ...utils import get_model_clean_name


@auto_register(
    ("title_label", "text", "widget.multi_connection.title"),
    ("_select_header_label", "text", "widget.multi_connection.select_header"),
    ("_connection_header_label", "text", "widget.multi_connection.connection_header"),
    ("_model_header_label", "text", "widget.multi_connection.model_header"),
    ("_select_all_btn", "text", "widget.multi_connection.select_all"),
    ("_deselect_all_btn", "text", "widget.multi_connection.deselect_all"),
)
class MultiConnectionTable(CardWidget):
    """Card for selecting multiple connections and their models."""

    connections_changed = QtCore.Signal(list)
    row_clicked = QtCore.Signal(str, str)
    model_changed = QtCore.Signal(str, str)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._row_widgets: list[dict] = []
        self._block_signals: bool = False
        self._selected_row_widget: QtWidgets.QWidget | None = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(6)

        self.title_label = StrongBodyLabel(self)
        main_layout.addWidget(self.title_label)

        header_layout = QtWidgets.QHBoxLayout()
        self._select_header_label = CaptionLabel(self)
        self._connection_header_label = CaptionLabel(self)
        self._model_header_label = CaptionLabel(self)
        header_layout.addWidget(self._select_header_label, 1)
        header_layout.addWidget(self._connection_header_label, 3)
        header_layout.addWidget(self._model_header_label, 4)
        main_layout.addLayout(header_layout)

        scroll_area = SmoothScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setMinimumHeight(90)
        self._rows_container = QtWidgets.QWidget()
        self._rows_layout = QtWidgets.QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        scroll_area.setWidget(self._rows_container)
        main_layout.addWidget(scroll_area)

        buttons_layout = QtWidgets.QHBoxLayout()
        self._select_all_btn = PushButton(self)
        self._deselect_all_btn = PushButton(self)
        self._select_all_btn.clicked.connect(self._select_all_custom)
        self._deselect_all_btn.clicked.connect(self._deselect_all_custom)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._select_all_btn)
        buttons_layout.addWidget(self._deselect_all_btn)
        main_layout.addLayout(buttons_layout)

    def _clear_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._row_widgets.clear()
        self._selected_row_widget = None

    def update_connections(self, restore_state: bool = False):
        self._block_signals = True
        self._clear_rows()

        custom_connections = settings.current_settings.get("custom_connections", [])
        active_model_for_connection = settings.current_settings.get(
            "active_model_for_connection", {}
        )

        for conn in custom_connections:
            conn_name = conn.get("name", "")
            if not conn_name:
                continue

            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(4)

            checkbox = CheckBox(row_widget)
            row_layout.addWidget(checkbox, 1)

            conn_label = BodyLabel(conn_name, row_widget)
            conn_label.setMinimumWidth(0)
            row_layout.addWidget(conn_label, 3)

            model_combo = ComboBox(row_widget)
            model_combo.setMinimumWidth(160)
            model_combo.setMaximumWidth(220)
            model_combo.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            for model_config in conn.get("configured_models", []):
                full_model_id = model_config.get("model_id", "")
                if full_model_id:
                    model_combo.addItem(
                        get_model_clean_name(full_model_id), userData=full_model_id
                    )

            last_model = active_model_for_connection.get(conn_name)
            if last_model:
                index = model_combo.findData(last_model)
                if index != -1:
                    model_combo.setCurrentIndex(index)
            elif model_combo.count() > 0:
                model_combo.setCurrentIndex(0)

            row_layout.addWidget(model_combo, 4)
            self._rows_layout.addWidget(row_widget)

            row_data = {
                "checkbox": checkbox,
                "combo": model_combo,
                "conn_name": conn_name,
                "row_widget": row_widget,
            }
            self._row_widgets.append(row_data)

            row_widget.mousePressEvent = (
                lambda event, rd=row_data: self._on_row_clicked(rd)
            )
            checkbox.toggled.connect(
                lambda checked, rd=row_data: self._on_checkbox_toggled(rd, checked)
            )
            model_combo.currentTextChanged.connect(
                lambda text, rd=row_data: self._on_model_combo_changed(rd, text)
            )

        self._rows_layout.addStretch()

        if restore_state:
            active_connections_list = settings.current_settings.get(
                "active_connections_list", []
            )
            active_conn_names = {
                conn_name for conn_name, _ in active_connections_list
            }

            for rd in self._row_widgets:
                conn_name = rd["conn_name"]
                if conn_name in active_conn_names:
                    saved_model_id = next(
                        (
                            model_id
                            for cn, model_id in active_connections_list
                            if cn == conn_name
                        ),
                        None,
                    )
                    rd["checkbox"].setChecked(True)
                    rd["combo"].setEnabled(True)

                    if saved_model_id:
                        index = rd["combo"].findData(saved_model_id)
                        if index != -1:
                            rd["combo"].setCurrentIndex(index)

            active_conn_name = settings.current_settings.get(
                "active_connection_name", ""
            )
            if active_conn_name:
                for rd in self._row_widgets:
                    if rd["conn_name"] == active_conn_name:
                        self._set_selection_highlight(rd["row_widget"])
                        break

        self._block_signals = False

    def _on_checkbox_toggled(self, row_data: dict, checked: bool):
        if self._block_signals:
            return

        active = self.get_active_connections()
        self.connections_changed.emit(active)
        settings.current_settings["active_connections_list"] = active
        settings.save_settings()

        if checked:
            row_data["combo"].setEnabled(True)
            conn_name = row_data["conn_name"]
            model_id = row_data["combo"].currentData() or row_data["combo"].currentText()
            self.row_clicked.emit(conn_name, model_id)
            settings.current_settings["active_connection_name"] = conn_name
            if self.main_window:
                self.main_window.set_active_connection_name(conn_name)
        elif not active:
            settings.current_settings["active_connection_name"] = None
            settings.save_settings()
            if self.main_window:
                self.main_window.set_active_connection_name(None)

    def _on_model_combo_changed(self, row_data: dict, text: str):
        if self._block_signals:
            return
        conn_name = row_data["conn_name"]
        model_id = row_data["combo"].currentData() or text
        settings.current_settings.setdefault("active_model_for_connection", {})[
            conn_name
        ] = model_id
        self.model_changed.emit(conn_name, model_id)

    def _clear_selection_highlight(self):
        if self._selected_row_widget:
            self._selected_row_widget.setStyleSheet("")
            self._selected_row_widget = None

    def _set_selection_highlight(self, row_widget: QtWidgets.QWidget):
        self._clear_selection_highlight()
        row_widget.setStyleSheet(
            "background-color: #2d2d30; border-radius: 4px;"
        )
        self._selected_row_widget = row_widget

    def _on_row_clicked(self, row_data: dict):
        conn_name = row_data["conn_name"]
        model_id = row_data["combo"].currentData() or row_data["combo"].currentText()
        self._set_selection_highlight(row_data["row_widget"])
        self.row_clicked.emit(conn_name, model_id)

    def _update_checkboxes_enabled(self, enabled: bool):
        for rd in self._row_widgets:
            rd["checkbox"].setEnabled(enabled)
            rd["combo"].setEnabled(enabled and rd["checkbox"].isChecked())

    def get_active_connections(self) -> list[tuple[str, str]]:
        result = []
        for rd in self._row_widgets:
            if rd["checkbox"].isChecked():
                conn_name = rd["conn_name"]
                model_id = rd["combo"].currentData() or rd["combo"].currentText()
                result.append((conn_name, model_id))
        return result

    def is_model_selected(self) -> bool:
        return any(
            rd["checkbox"].isChecked()
            and bool(rd["combo"].currentData() or rd["combo"].currentText())
            for rd in self._row_widgets
        )

    def _select_all_custom(self):
        self._block_signals = True
        for rd in self._row_widgets:
            rd["checkbox"].setChecked(True)
            rd["combo"].setEnabled(True)
        self._block_signals = False
        active = self.get_active_connections()
        self.connections_changed.emit(active)
        settings.current_settings["active_connections_list"] = active
        settings.save_settings()

    def _deselect_all_custom(self):
        self._block_signals = True
        for rd in self._row_widgets:
            rd["checkbox"].setChecked(False)
            rd["combo"].setEnabled(False)
        self._block_signals = False
        self._clear_selection_highlight()
        self.connections_changed.emit([])
        settings.current_settings["active_connections_list"] = []
        settings.current_settings["active_connection_name"] = None
        settings.save_settings()
        if self.main_window:
            self.main_window.set_active_connection_name(None)
