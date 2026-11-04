from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    Dialog,
    FluentIcon,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    SpinBox,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    TransparentToolButton,
)

from ... import settings
from ...localization_manager import translate, auto_register
from ...proxy_manager import proxy_manager


PROXY_PROTOCOLS = ("HTTP", "HTTPS", "SOCKS5")
PROXY_TABLE_COLUMNS = 5


@auto_register(
    # Enable proxy switch
    ("proxy_enabled_check", "text", "dialog.settings.proxy.enabled_check"),

    # Custom proxies card
    ("custom_proxy_title", "text", "dialog.settings.proxy.custom_group"),

    # Table headers
    ("proxy_table", "horizontalHeaderKeys", (
        "dialog.settings.proxy.header_num",
        "dialog.settings.proxy.header_protocol",
        "dialog.settings.proxy.header_address",
        "dialog.settings.proxy.header_auth",
        "dialog.settings.proxy.header_actions",
    )),

    # Add proxy card
    ("add_proxy_title", "text", "dialog.settings.proxy.add_group"),
    ("proxy_auth_label", "text", "dialog.settings.proxy.require_auth"),
    ("proxy_test_btn", "text", "dialog.settings.proxy.test_button"),
    ("proxy_add_btn", "text", "dialog.settings.proxy.add_button"),
    ("proxy_test_status_label", "text", "dialog.settings.proxy.test_status_idle"),
)

class ProxyTabWidget(QtWidgets.QWidget):
    """Proxy settings tab with auto-registered localizations."""

    # Signals for communication with parent dialog
    proxy_added = QtCore.Signal(dict)
    proxy_removed = QtCore.Signal(int)
    proxy_test_requested = QtCore.Signal(str)

    def __init__(self, settings_data: dict, parent=None):
        super().__init__(parent)
        self.settings_data = settings_data
        self._setup_ui()

    def _setup_ui(self):
        """Create all UI elements."""
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = SmoothScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        root_layout.addWidget(scroll_area)

        content = QtWidgets.QWidget()
        scroll_area.setWidget(content)

        main_layout = QtWidgets.QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # --- Custom proxies card ---
        self.custom_proxy_group = CardWidget(content)
        custom_layout = QtWidgets.QVBoxLayout(self.custom_proxy_group)
        custom_layout.setContentsMargins(16, 10, 16, 10)
        custom_layout.setSpacing(6)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(8)
        self.custom_proxy_title = StrongBodyLabel(self.custom_proxy_group)
        header_layout.addWidget(self.custom_proxy_title)
        header_layout.addStretch(1)

        # Enable proxy switch lives in the card header, so the tab stays compact
        self.proxy_enabled_check = SwitchButton(self.custom_proxy_group)
        self.proxy_enabled_check.setChecked(
            self.settings_data.get("proxy_enabled", False)
        )
        header_layout.addWidget(self.proxy_enabled_check)
        custom_layout.addLayout(header_layout)

        self.proxy_table = TableWidget(self.custom_proxy_group)
        self.proxy_table.setColumnCount(PROXY_TABLE_COLUMNS)
        # Заголовки будут установлены через локализацию
        self.proxy_table.setHorizontalHeaderLabels([""] * PROXY_TABLE_COLUMNS)
        self.proxy_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.proxy_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.proxy_table.setWordWrap(False)
        self.proxy_table.setBorderVisible(True)
        self.proxy_table.setMinimumHeight(64)
        self.proxy_table.verticalHeader().setVisible(False)
        self.proxy_table.verticalHeader().setDefaultSectionSize(36)

        header = self.proxy_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        custom_layout.addWidget(self.proxy_table, 1)
        self._populate_proxy_table()

        main_layout.addWidget(self.custom_proxy_group, 1)

        # --- Add proxy card ---
        self.add_proxy_group = CardWidget(content)
        add_layout = QtWidgets.QGridLayout(self.add_proxy_group)
        add_layout.setContentsMargins(16, 10, 16, 10)
        add_layout.setHorizontalSpacing(10)
        add_layout.setVerticalSpacing(6)
        add_layout.setColumnStretch(1, 1)
        add_layout.setColumnStretch(3, 0)

        self.add_proxy_title = StrongBodyLabel(self.add_proxy_group)
        add_layout.addWidget(self.add_proxy_title, 0, 0, 1, 4)

        # Protocol / port row
        self.new_proxy_protocol = ComboBox(self.add_proxy_group)
        self.new_proxy_protocol.addItems(list(PROXY_PROTOCOLS))
        self.new_proxy_protocol.setMinimumWidth(110)
        add_layout.addWidget(
            BodyLabel(translate("dialog.settings.proxy.protocol_label"), self.add_proxy_group),
            1, 0,
        )
        add_layout.addWidget(self.new_proxy_protocol, 1, 1)

        self.new_proxy_port = SpinBox(self.add_proxy_group)
        self.new_proxy_port.setRange(1, 65535)
        self.new_proxy_port.setValue(8080)
        self.new_proxy_port.setFixedWidth(100)
        add_layout.addWidget(
            BodyLabel(translate("dialog.settings.proxy.port_label"), self.add_proxy_group),
            1, 2,
        )
        add_layout.addWidget(self.new_proxy_port, 1, 3)

        # Host row
        self.new_proxy_host = LineEdit(self.add_proxy_group)
        self.new_proxy_host.setPlaceholderText(
            translate("dialog.settings.proxy.host_placeholder")
        )
        self.new_proxy_host.setClearButtonEnabled(True)
        add_layout.addWidget(
            BodyLabel(translate("dialog.settings.proxy.host_label"), self.add_proxy_group),
            2, 0,
        )
        add_layout.addWidget(self.new_proxy_host, 2, 1, 1, 3)

        # Auth switch + credentials row
        self.proxy_auth_label = BodyLabel(
            translate("dialog.settings.proxy.require_auth"), self.add_proxy_group
        )
        self.proxy_auth_label.setWordWrap(True)
        add_layout.addWidget(self.proxy_auth_label, 3, 0)

        self.proxy_auth_check = SwitchButton(self.add_proxy_group)
        add_layout.addWidget(self.proxy_auth_check, 3, 1)

        credentials = QtWidgets.QWidget(self.add_proxy_group)
        credentials_layout = QtWidgets.QHBoxLayout(credentials)
        credentials_layout.setContentsMargins(0, 0, 0, 0)
        credentials_layout.setSpacing(8)

        self.new_proxy_user = LineEdit(credentials)
        self.new_proxy_user.setPlaceholderText(
            translate("dialog.settings.proxy.username_placeholder")
        )
        self.new_proxy_user.setEnabled(False)

        self.new_proxy_pass = LineEdit(credentials)
        self.new_proxy_pass.setPlaceholderText(
            translate("dialog.settings.proxy.password_placeholder")
        )
        self.new_proxy_pass.setEchoMode(LineEdit.EchoMode.Password)
        self.new_proxy_pass.setEnabled(False)

        self.proxy_auth_check.checkedChanged.connect(self.new_proxy_user.setEnabled)
        self.proxy_auth_check.checkedChanged.connect(self.new_proxy_pass.setEnabled)

        credentials_layout.addWidget(self.new_proxy_user)
        credentials_layout.addWidget(self.new_proxy_pass)
        add_layout.addWidget(credentials, 3, 2, 1, 2)

        # Test status + actions
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.proxy_test_status_label = BodyLabel(self.add_proxy_group)
        self.proxy_test_status_label.setWordWrap(True)
        self.proxy_test_status_label.setStyleSheet("color: #888; font-style: italic;")

        self.proxy_test_btn = PushButton(self.add_proxy_group)
        self.proxy_test_btn.clicked.connect(self._test_new_proxy)
        self.proxy_add_btn = PrimaryPushButton(self.add_proxy_group)
        self.proxy_add_btn.clicked.connect(self._add_custom_proxy)

        btn_layout.addWidget(self.proxy_test_status_label, 1)
        btn_layout.addWidget(self.proxy_test_btn)
        btn_layout.addWidget(self.proxy_add_btn)
        add_layout.addLayout(btn_layout, 4, 0, 1, 4)

        main_layout.addWidget(self.add_proxy_group)
        main_layout.addStretch()

    def _populate_proxy_table(self):
        """Fill the custom proxies table."""
        proxies = self.settings_data.get("proxy_custom_list", [])
        self.proxy_table.setRowCount(len(proxies))

        for row, p in enumerate(proxies):
            self.proxy_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(row + 1)))
            self.proxy_table.setItem(row, 1, QtWidgets.QTableWidgetItem(p.get("protocol", "http").upper()))

            addr = f"{p.get('host', '')}:{p.get('port', '')}"
            self.proxy_table.setItem(row, 2, QtWidgets.QTableWidgetItem(addr))

            auth = f"{p.get('username', '')}:***" if p.get("username") else "—"
            self.proxy_table.setItem(row, 3, QtWidgets.QTableWidgetItem(auth))

            # Delete button
            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 0, 4, 0)
            actions_layout.setSpacing(0)

            del_btn = TransparentToolButton(FluentIcon.DELETE, actions_widget)
            del_btn.setFixedSize(28, 28)
            del_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip(translate("dialog.settings.proxy.header_actions"))
            del_btn.clicked.connect(lambda _, r=row: self._remove_custom_proxy(r))

            actions_layout.addWidget(del_btn)
            actions_layout.addStretch()
            self.proxy_table.setCellWidget(row, 4, actions_widget)

    def _add_custom_proxy(self):
        """Add proxy from form to list."""
        host = self.new_proxy_host.text().strip()
        if not host:
            MessageBox(
                "Error",
                translate("dialog.settings.proxy.error_enter_host"),
                self,
            ).exec()
            return

        port = self.new_proxy_port.value()

        entry = {
            "protocol": self.new_proxy_protocol.currentText().lower(),
            "host": host,
            "port": port,
            "username": self.new_proxy_user.text().strip() if self.proxy_auth_check.isChecked() else "",
            "password": self.new_proxy_pass.text() if self.proxy_auth_check.isChecked() else "",
        }

        if "proxy_custom_list" not in self.settings_data:
            self.settings_data["proxy_custom_list"] = []
        self.settings_data["proxy_custom_list"].append(entry)

        self._populate_proxy_table()
        self.new_proxy_host.clear()
        self.new_proxy_port.setValue(8080)
        self.new_proxy_user.clear()
        self.new_proxy_pass.clear()
        self.proxy_auth_check.setChecked(False)

        self.proxy_added.emit(entry)

    def _remove_custom_proxy(self, row: int):
        """Remove proxy from list."""
        proxies = self.settings_data.get("proxy_custom_list", [])
        if 0 <= row < len(proxies):
            del self.settings_data["proxy_custom_list"][row]
            self._populate_proxy_table()
            self.proxy_removed.emit(row)

    def _test_new_proxy(self):
        """Test the proxy entered in the form."""
        from ...proxy_manager import proxy_manager

        host = self.new_proxy_host.text().strip()
        if not host:
            self._set_test_status(translate("dialog.settings.proxy.test_status_error_no_host"), success=False)
            return

        port = self.new_proxy_port.value()
        protocol = self.new_proxy_protocol.currentText().lower()

        if self.proxy_auth_check.isChecked():
            user = self.new_proxy_user.text().strip()
            pwd = self.new_proxy_pass.text()
            proxy_url = f"{protocol}://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = f"{protocol}://{host}:{port}"

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            success, msg, speed_ms = proxy_manager.validate_proxy(proxy_url, timeout=10)
            if success:
                self._set_test_status(
                    f"{translate('dialog.settings.proxy.test_success')} — {msg} ({speed_ms} ms)",
                    success=True
                )
            else:
                self._set_test_status(
                    f"{translate('dialog.settings.proxy.test_fail')}: {msg}",
                    success=False
                )
        except Exception as e:
            self._set_test_status(
                f"{translate('dialog.settings.proxy.test_fail')}: {e}",
                success=False
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _set_test_status(self, text: str, success: bool):
        """Set the test result status label."""
        if hasattr(self, 'proxy_test_status_label'):
            self.proxy_test_status_label.setText(text)
            if success:
                self.proxy_test_status_label.setStyleSheet("color: #50fa7b; font-weight: bold;")
            else:
                self.proxy_test_status_label.setStyleSheet("color: #ff5555; font-weight: bold;")

    def _check_connection(self):
        """Test proxy connection and show results."""
        from ...proxy_manager import proxy_manager

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            proxy_url = proxy_manager.get_proxy()
            if proxy_url:
                success, msg, _ = proxy_manager.validate_proxy(proxy_url, timeout=10)
                if success:
                    MessageBox(
                        translate("dialog.settings.proxy.check_connection_title"),
                        f"{translate('dialog.settings.proxy.check_connection_success')}\n{msg}",
                        self,
                    ).exec()
                else:
                    MessageBox(
                        translate("dialog.settings.proxy.check_connection_title"),
                        f"{translate('dialog.settings.proxy.check_connection_fail')}\n{msg}",
                        self,
                    ).exec()
            else:
                count = len(self.settings_data.get("proxy_custom_list", []))
                MessageBox(
                    translate("dialog.settings.proxy.check_connection_title"),
                    translate("dialog.settings.proxy.check_connection_no_proxy", count=count),
                    self,
                ).exec()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def get_proxy_settings(self) -> dict:
        """Get current proxy settings from the tab."""
        return {
            "proxy_enabled": self.proxy_enabled_check.isChecked(),
            "proxy_custom_list": self.settings_data.get("proxy_custom_list", []),
        }


class ProxyDialog(Dialog):
    def __init__(self, parent=None):
        super().__init__("Proxy", "", parent)
        self.setFixedSize(560, 560)
        self.contentLabel.hide()
        self.yesButton.setText("Save")
        self.cancelButton.setText("Close")
        self.proxy_tab = ProxyTabWidget(settings.current_settings, self)
        self.textLayout.addWidget(self.proxy_tab, 1)

    def accept(self) -> None:
        settings.current_settings.update(self.proxy_tab.get_proxy_settings())
        settings.save_settings()
        super().accept()
