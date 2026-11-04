import logging
from ..localization_manager import auto_register
from .. import constants as const
from PySide6 import QtWidgets, QtCore, QtGui

logger = logging.getLogger('CORE_UI.animations')

class UIAnimator:
    @staticmethod
    def shake_widget(
        widget: QtWidgets.QWidget,
        shake_amount: int = const.DEFAULT_SHAKE_AMOUNT,
        duration_ms: int = const.DEFAULT_SHAKE_DURATION_MS,
    ):
        existing_anim = widget.findChild(QtCore.QPropertyAnimation, "shake_anim")
        if (
            existing_anim
            and existing_anim.state() == QtCore.QAbstractAnimation.State.Running
        ):
            return
        pos = widget.pos()
        animation = QtCore.QPropertyAnimation(widget, b"pos", parent=widget)
        animation.setObjectName("shake_anim")
        animation.setDuration(duration_ms)
        animation.setLoopCount(2)
        animation.setKeyValueAt(0.0, pos)
        animation.setKeyValueAt(0.1, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(0.2, pos)
        animation.setKeyValueAt(0.3, pos + QtCore.QPoint(-shake_amount, 0))
        animation.setKeyValueAt(0.4, pos)
        animation.setKeyValueAt(0.5, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(0.6, pos)
        animation.setKeyValueAt(0.7, pos + QtCore.QPoint(-shake_amount, 0))
        animation.setKeyValueAt(0.8, pos)
        animation.setKeyValueAt(0.9, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(1.0, pos)
        animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def flash_status_label(
        label: QtWidgets.QLabel,
        text: str,
        color: str = const.FLASH_SUCCESS_COLOR,
        duration_ms: int = const.DEFAULT_FLASH_DURATION_MS,
    ):
        label.setText(text)
        label.setStyleSheet(f"color: {color};")
        effect = label.graphicsEffect()
        if not isinstance(effect, QtWidgets.QGraphicsOpacityEffect):
            effect = QtWidgets.QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
        old_anim = label.findChild(QtCore.QSequentialAnimationGroup)
        if old_anim:
            old_anim.stop()
            old_anim.deleteLater()
        seq_anim = QtCore.QSequentialAnimationGroup(label)
        anim_in = QtCore.QPropertyAnimation(effect, b"opacity")
        anim_in.setDuration(const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_out = QtCore.QPropertyAnimation(effect, b"opacity")
        anim_out.setDuration(500)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        seq_anim.addAnimation(anim_in)
        seq_anim.addPause(duration_ms)
        seq_anim.addAnimation(anim_out)
        seq_anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    @staticmethod
    def flash_table_row(
        table: QtWidgets.QTableWidget,
        rows: int | list[int],
        highlight_color_hex: str = const.DEFAULT_TABLE_ROW_HIGHLIGHT_COLOR,
        duration_ms: int = const.DEFAULT_TABLE_ROW_FLASH_DURATION_MS,
    ):
        if isinstance(rows, int):
            rows_to_process = [rows]
        else:
            rows_to_process = rows
        valid_rows = {r for r in rows_to_process if 0 <= r < table.rowCount()}
        if not valid_rows:
            logger.debug("[flash_table_row] No valid rows, returning early.")
            return
        selection_model = table.selectionModel()
        selected_rows = {index.row() for index in selection_model.selectedRows()}
        highlight_color = QtGui.QColor(highlight_color_hex)
        selection_color = QtGui.QColor(const.TABLE_SELECTION_COLOR_HEX)
        all_items_to_animate = []
        coord_to_start_color_map = {}
        for row in valid_rows:
            items_in_row = []
            is_row_selected = row in selected_rows
            start_color = (
                selection_color if is_row_selected else QtGui.QColor(0, 0, 0, 0)
            )
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    table.setItem(row, col, item)
                items_in_row.append(item)
                coord_to_start_color_map[(row, col)] = start_color
            if items_in_row:
                old_animation = items_in_row[0].data(
                    QtCore.Qt.ItemDataRole.UserRole + 1
                )
                if (
                    isinstance(old_animation, QtCore.QAbstractAnimation)
                    and old_animation.state() == QtCore.QAbstractAnimation.State.Running
                ):
                    logger.debug(f"[flash_table_row] Stopping old animation for row {row}")
                    old_animation.stop()
            all_items_to_animate.extend(items_in_row)
        logger.debug(f"[flash_table_row] Total items to animate: {len(all_items_to_animate)}")
        if selected_rows:
            selection_model.blockSignals(True)
            selection_model.clear()
            non_flashing_selected_rows = selected_rows - valid_rows
            for r in non_flashing_selected_rows:
                for c in range(table.columnCount()):
                    if item := table.item(r, c):
                        item.setBackground(selection_color)
            for item in all_items_to_animate:
                start_color = coord_to_start_color_map.get((item.row(), item.column()))
                if start_color:
                    item.setBackground(start_color)
            selection_model.blockSignals(False)
        animation_group = QtCore.QParallelAnimationGroup(table)
        for item in all_items_to_animate:
            start_color = coord_to_start_color_map.get((item.row(), item.column()))
            if not start_color:
                continue
            sequential_anim = QtCore.QSequentialAnimationGroup(animation_group)
            fade_in_anim = QtCore.QVariantAnimation(sequential_anim)
            fade_in_anim.setDuration(duration_ms // 2)
            fade_in_anim.setStartValue(start_color)
            fade_in_anim.setEndValue(highlight_color)
            fade_in_anim.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
            fade_out_anim = QtCore.QVariantAnimation(sequential_anim)
            fade_out_anim.setDuration(duration_ms // 2)
            fade_out_anim.setStartValue(highlight_color)
            fade_out_anim.setEndValue(start_color)
            fade_out_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutQuad)
            sequential_anim.addAnimation(fade_in_anim)
            sequential_anim.addAnimation(fade_out_anim)

            def create_update_func(it):
                return lambda color: it.setBackground(QtGui.QBrush(color))

            update_func = create_update_func(item)
            fade_in_anim.valueChanged.connect(update_func)
            fade_out_anim.valueChanged.connect(update_func)
            animation_group.addAnimation(sequential_anim)

        def on_group_finished():
            logger.debug("[flash_table_row] Animation group finished.")
            if all_items_to_animate:
                all_items_to_animate[0].setData(QtCore.Qt.UserRole + 1, None)
            rows_we_touched = selected_rows | valid_rows
            for r in rows_we_touched:
                for c in range(table.columnCount()):
                    if item := table.item(r, c):
                        item.setBackground(QtGui.QBrush())
            if selected_rows:
                selection_model.blockSignals(True)
                selection_model.clear()
                for r in selected_rows:
                    selection_model.select(
                        table.model().index(r, 0),
                        QtCore.QItemSelectionModel.Select
                        | QtCore.QItemSelectionModel.Rows,
                    )
                selection_model.blockSignals(False)

        animation_group.finished.connect(on_group_finished)
        logger.debug(f"[flash_table_row] Starting animation group with {animation_group.animationCount()} animations.")
        animation_group.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
        if all_items_to_animate:
            all_items_to_animate[0].setData(QtCore.Qt.UserRole + 1, animation_group)
        logger.debug("[flash_table_row] Animation started.")

    @staticmethod
    def toggle_visibility_animated(
        widget: QtWidgets.QWidget,
        show: bool,
        duration_ms: int = const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS,
    ):
        anim = QtCore.QPropertyAnimation(widget, b"maximumWidth", parent=widget)
        anim.setDuration(duration_ms)
        if show:
            widget.show()
            target_width = widget.sizeHint().width()
            anim.setStartValue(0)
            anim.setEndValue(target_width)
        else:
            start_width = widget.width()
            anim.setStartValue(start_width)
            anim.setEndValue(0)
            anim.finished.connect(widget.hide)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def toggle_visibility_animated_vertical(
        widget: QtWidgets.QWidget,
        show: bool,
        duration_ms: int = const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS,
    ):
        anim = QtCore.QPropertyAnimation(widget, b"maximumHeight", parent=widget)
        anim.setDuration(duration_ms)
        if show:
            widget.show()
            target_height = widget.sizeHint().height()
            anim.setStartValue(0)
            anim.setEndValue(target_height)
        else:
            start_height = widget.height()
            anim.setStartValue(start_height)
            anim.setEndValue(0)
            anim.finished.connect(widget.hide)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        return anim
