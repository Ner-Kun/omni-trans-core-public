from PySide6.QtCore import Qt, Property, QRect
from PySide6 import QtWidgets
from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QPainter

class SmartButton(QPushButton):
    STATE_NO_SELECTION = "no_selection"
    STATE_NOT_INSTALLED = "not_installed"
    STATE_INSTALLED = "installed"
    STATE_BUSY = "busy"
    STATE_CLOSING = "closing"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 50)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("ActionButton")
        self._current_state = self.STATE_NO_SELECTION
        self.update_state(self.STATE_NO_SELECTION)

    def update_state(self, state: str, text: str = None):
        self._current_state = state
        self.setEnabled(True)

        self.setProperty("state", state)

        if state == self.STATE_NO_SELECTION:
            self.setText("Select App")
            self.setEnabled(False)
        elif state == self.STATE_NOT_INSTALLED:
            self.setText("DOWNLOAD")
        elif state == self.STATE_INSTALLED:
            self.setText("LAUNCH")
        elif state == self.STATE_BUSY:
            self.setText(text if text else "Working...")
            self.setEnabled(False)
        elif state == self.STATE_CLOSING:
            self.setText(text if text else "Closing...")
            self.setEnabled(False)

        self.style().unpolish(self)
        self.style().polish(self)
        
class AnimatedIconButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_scale = 1.0
        self._icon_rotation = 0.0
        self._y_offset = 0.0
        self._x_offset = 0.0

    def get_icon_scale(self):
        return self._icon_scale

    def set_icon_scale(self, val):
        self._icon_scale = val
        self.update()
    def get_icon_rotation(self):
        return self._icon_rotation

    def set_icon_rotation(self, val):
        self._icon_rotation = val
        self.update()

    def get_y_offset(self):
        return self._y_offset

    def set_y_offset(self, val):
        self._y_offset = val
        self.update()

    def get_x_offset(self):
        return self._x_offset

    def set_x_offset(self, val):
        self._x_offset = val
        self.update()

    p_icon_scale = Property(float, get_icon_scale, set_icon_scale)
    p_icon_rotation = Property(float, get_icon_rotation, set_icon_rotation)
    p_y_offset = Property(float, get_y_offset, set_y_offset)
    p_x_offset = Property(float, get_x_offset, set_x_offset)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        opt = QtWidgets.QStyleOptionButton()
        self.initStyleOption(opt)

        self.style().drawPrimitive(
            QtWidgets.QStyle.PE_PanelButtonCommand, opt, painter, self
        )
        
        if self.icon().isNull():
            return

        icon_size = self.iconSize()
        rect = self.rect()

        cx = rect.width() / 2
        cy = rect.height() / 2

        painter.save()

        painter.translate(cx + self._x_offset, cy + self._y_offset)
        painter.rotate(self._icon_rotation)
        painter.scale(self._icon_scale, self._icon_scale)

        pixmap = self.icon().pixmap(icon_size)

        target_rect = QRect(
            int(-icon_size.width() / 2),
            int(-icon_size.height() / 2),
            icon_size.width(),
            icon_size.height(),
        )
        painter.drawPixmap(target_rect, pixmap)

        painter.restore()
