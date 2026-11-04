import logging
from PySide6 import QtWidgets, QtCore, QtGui
from qfluentwidgets import LineEdit, TableWidget, TextEdit

from .animations import UIAnimator

logger = logging.getLogger('CORE_UI.base_widgets')


def fix_spin_box_editor(spin: QtWidgets.QAbstractSpinBox) -> None:
    """Keep the Fluent SpinBox value visible under Qt 6.12.

    QFluentWidgets paints its own chevrons and switches Qt's spin buttons off;
    Qt 6.12 then collapses the internal editor to one pixel. Qt's buttons are
    restored for the editor geometry and collapsed to zero width, so the Fluent
    panel stays untouched.
    """
    spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows)
    spin.setStyleSheet(
        spin.styleSheet()
        + "\nQSpinBox::up-button, QSpinBox::down-button, "
        "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
        " width: 0px; border: none; background: transparent; }"
    )

class ShakeLineEdit(LineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.animation = QtCore.QPropertyAnimation(self, b"pos")

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        validator = self.validator()
        if not validator:
            super().keyPressEvent(event)
            return
        if event.key() in (QtCore.Qt.Key.Key_Backspace, QtCore.Qt.Key.Key_Delete):
            super().keyPressEvent(event)
            return
        if not event.text() or event.modifiers() & (
            QtCore.Qt.KeyboardModifier.ControlModifier
            | QtCore.Qt.KeyboardModifier.AltModifier
        ):
            super().keyPressEvent(event)
            return
        future_text = (
            self.text()[: self.cursorPosition()]
            + event.text()
            + self.text()[self.cursorPosition() :]
        )
        assert validator is not None
        state, _, _ = validator.validate(future_text, 0)
        if (
            state == QtGui.QValidator.State.Acceptable
            or state == QtGui.QValidator.State.Intermediate
        ):
            super().keyPressEvent(event)
        else:
            self._shake()
            event.accept()

    def _shake(self):
        UIAnimator.shake_widget(self)

class FocusOutTextEdit(TextEdit):
    focus_out = QtCore.Signal()

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        self.focus_out.emit()
        super().focusOutEvent(event)

class FilterableTableWidget(TableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._searchable_columns = []
        self._original_data_map = {}

    def set_searchable_columns(self, columns: list[int]):
        self._searchable_columns = columns

    def set_row_hidden_data(self, row: int, data: str):
        self._original_data_map[row] = data.lower()

    @QtCore.Slot(str)
    def filter(self, search_term: str):
        term = search_term.lower().strip()
        for row in range(self.rowCount()):
            should_be_visible = False
            if not term:
                should_be_visible = True
            else:
                columns_to_search = self._searchable_columns or range(
                    self.columnCount()
                )
                for col in columns_to_search:
                    item = self.item(row, col)
                    if item and term in item.text().lower():
                        should_be_visible = True
                        break
                if not should_be_visible and row in self._original_data_map:
                    if term in self._original_data_map[row]:
                        should_be_visible = True
            self.setRowHidden(row, not should_be_visible)
