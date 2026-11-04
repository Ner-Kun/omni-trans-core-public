import logging

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import SearchLineEdit

from ...localization_manager import auto_register, translate
from ..animations import UIAnimator
from ..base_widgets import FilterableTableWidget

logger = logging.getLogger('CORE_UI.widgets')

@auto_register(
    ("search_input", "placeholderText", "widget.searchable_table.search_placeholder"),
)
class DataTableWidget(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns_config = []
        self._data = []
        self._unique_id_key = None
        self._id_to_row_map = {}
        self._row_to_id_map = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = SearchLineEdit()
        self.table = FilterableTableWidget()
        layout.addWidget(self.search_input)
        layout.addWidget(self.table)
        self.search_input.textChanged.connect(self.table.filter)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def configure(self, columns: list[dict]):
        self._columns_config = columns
        self.table.setColumnCount(len(columns))
        self._apply_column_headers()
        header_view = self.table.horizontalHeader()
        for i, col_config in enumerate(columns):
            resize_mode = col_config.get('resize_mode', QtWidgets.QHeaderView.ResizeMode.Interactive)
            header_view.setSectionResizeMode(i, resize_mode)

    def _apply_column_headers(self):
        """Apply translated headers from column config."""
        headers = []
        for col in self._columns_config:
            if "header_key" in col:
                headers.append(translate(col["header_key"]))
            else:
                headers.append(col.get("header", ""))
        self.table.setHorizontalHeaderLabels(headers)

    def retranslate_ui(self):
        """Re-apply column headers with current translations."""
        self._apply_column_headers()

    def set_data(self, data: list[dict], unique_id_key: str):
        self._data = data
        self._unique_id_key = unique_id_key
        self._id_to_row_map.clear()
        self._row_to_id_map.clear()
        self.table.setRowCount(0)
        if not data:
            return
        self.table.setRowCount(len(data))
        try:
            self.table.setUpdatesEnabled(False)
            for row_idx, row_data in enumerate(data):
                row_id = row_data.get(unique_id_key)
                if row_id is None:
                    logger.warning("DataTableWidget.set_data: row at index %d has no '%s' key, skipping", row_idx, unique_id_key)
                    continue
                self._id_to_row_map[row_id] = row_idx
                self._row_to_id_map[row_idx] = row_id
                full_search_text_parts = []
                for col_idx, col_config in enumerate(self._columns_config):
                    data_key = col_config.get('key')
                    if not data_key:
                        continue
                    cell_value = str(row_data.get(data_key, ''))
                    item = QtWidgets.QTableWidgetItem(cell_value)
                    self.table.setItem(row_idx, col_idx, item)
                    full_search_text_parts.append(cell_value)
                self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))
        finally:
            self.table.setUpdatesEnabled(True)

    def update_row_by_id(self, row_id, new_row_data: dict):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is None:
            return
        self._data[row_idx].update(new_row_data)
        full_search_text_parts = []
        for col_idx, col_config in enumerate(self._columns_config):
            data_key = col_config.get('key')
            if not data_key:
                continue
            cell_value = str(self._data[row_idx].get(data_key, ''))
            item = self.table.item(row_idx, col_idx)
            if item:
                item.setText(cell_value)
            else:
                self.table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(cell_value))
            full_search_text_parts.append(cell_value)
        self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))

    def get_selected_rows_data(self) -> list[dict]:
        selected_rows_indices = {idx.row() for idx in self.table.selectedIndexes()}
        if not selected_rows_indices:
            return []
        selected_data = []
        for row_idx in sorted(list(selected_rows_indices)):
            row_id = self._row_to_id_map.get(row_idx)
            if row_id:
                selected_data.append(self._data[row_idx])
        return selected_data

    def flash_row_by_id(self, row_ids: str | list[str], color: str | None = None):
        if isinstance(row_ids, str):
            ids_to_process = [row_ids]
        else:
            ids_to_process = row_ids
        row_indices = []
        for row_id in ids_to_process:
            row_idx = self._id_to_row_map.get(row_id)
            if row_idx is not None:
                row_indices.append(row_idx)
        if not row_indices:
            return
        if color:
            UIAnimator.flash_table_row(self.table, row_indices, highlight_color_hex=color)
        else:
            UIAnimator.flash_table_row(self.table, row_indices)

    def scroll_to_row_by_id(self, row_id):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is not None:
            item = self.table.item(row_idx, 0)
            if item:
                self.table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    @QtCore.Slot()
    def _on_selection_changed(self):
        selected_data = self.get_selected_rows_data()
        self.selection_changed.emit(selected_data)
