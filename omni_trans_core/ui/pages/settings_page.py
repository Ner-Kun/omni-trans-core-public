from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    PushSettingCard,
    SettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SpinBox,
    SwitchSettingCard,
    TitleLabel,
)


class SettingsPage(QWidget):
    language_changed = Signal(str)
    logging_changed = Signal()
    general_settings_changed = Signal()
    connections_requested = Signal()
    proxy_requested = Signal()
    cache_clear_requested = Signal()
    translation_mode_changed = Signal(bool)

    def __init__(
        self,
        settings_data: dict,
        languages: list[dict[str, str]],
        dev_tools_available: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.settings_data = settings_data

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("settingsContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(12)
        layout.addWidget(TitleLabel("Settings", container))

        layout.addWidget(self._build_interface_group(container, languages))
        layout.addWidget(self._build_providers_group(container))
        layout.addWidget(self._build_behavior_group(container))
        layout.addWidget(self._build_logging_group(container))
        layout.addWidget(self._build_maintenance_group(container))
        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        if dev_tools_available:
            self.translation_mode_card.setChecked(
                bool(settings_data.get("translation_mode_enabled", False))
            )

    def _build_interface_group(self, parent, languages):
        group = SettingCardGroup("Interface", parent)

        self.language_card = SettingCard(
            FluentIcon.LANGUAGE,
            "Language",
            "Interface language",
            group,
        )
        self.language_combo = ComboBox(self.language_card)
        for language in languages:
            self.language_combo.addItem(
                language["name"], userData=language["code"]
            )
        current_language = self.settings_data.get("user_language", "en")
        index = self.language_combo.findData(current_language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.language_card.hBoxLayout.addWidget(
            self.language_combo, 0, Qt.AlignmentFlag.AlignRight
        )
        self.language_card.hBoxLayout.addSpacing(16)
        group.addSettingCard(self.language_card)

        self.translation_mode_card = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            "Translation mode",
            "Show the localization toolbar for interface testing.",
            None,
            group,
        )
        self.translation_mode_card.setChecked(
            bool(self.settings_data.get("translation_mode_enabled", False))
        )
        self.translation_mode_card.checkedChanged.connect(
            self._on_translation_mode_changed
        )
        group.addSettingCard(self.translation_mode_card)
        return group

    def _build_providers_group(self, parent):
        group = SettingCardGroup("Providers", parent)

        self.connections_card = PushSettingCard(
            "Open",
            FluentIcon.LINK,
            "Manage connections",
            "Add, edit or remove translation providers.",
            group,
        )
        self.connections_card.clicked.connect(self.connections_requested)
        group.addSettingCard(self.connections_card)

        self.proxy_card = PushSettingCard(
            "Open",
            FluentIcon.GLOBE,
            "Proxy",
            "Configure proxies for API requests.",
            group,
        )
        self.proxy_card.clicked.connect(self.proxy_requested)
        group.addSettingCard(self.proxy_card)
        return group

    def _build_behavior_group(self, parent):
        group = SettingCardGroup("Behavior", parent)

        self.auto_save_card = SettingCard(
            FluentIcon.SAVE,
            "Auto-save",
            "Save changes automatically after N seconds; 0 disables.",
            group,
        )
        self.auto_save_spin = SpinBox(self.auto_save_card)
        self.auto_save_spin.setRange(0, 300)
        self.auto_save_spin.setSuffix(" s")
        self.auto_save_spin.setValue(
            int(self.settings_data.get("auto_save_interval_ms", 5000)) // 1000
        )
        self.auto_save_spin.valueChanged.connect(self._on_auto_save_changed)
        self.auto_save_card.hBoxLayout.addWidget(
            self.auto_save_spin, 0, Qt.AlignmentFlag.AlignRight
        )
        self.auto_save_card.hBoxLayout.addSpacing(16)
        group.addSettingCard(self.auto_save_card)

        self.api_workers_card = SettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            "API workers",
            "Number of parallel API requests.",
            group,
        )
        self.api_workers_spin = SpinBox(self.api_workers_card)
        max_threads = max(1, QThreadPool.globalInstance().maxThreadCount())
        self.api_workers_spin.setRange(1, max_threads)
        ratio = float(self.settings_data.get("api_thread_pool_ratio", 0.75))
        self.api_workers_spin.setValue(max(1, round(ratio * max_threads)))
        self.api_workers_spin.valueChanged.connect(self._on_api_workers_changed)
        self.api_workers_card.hBoxLayout.addWidget(
            self.api_workers_spin, 0, Qt.AlignmentFlag.AlignRight
        )
        self.api_workers_card.hBoxLayout.addSpacing(16)
        group.addSettingCard(self.api_workers_card)
        return group

    def _build_logging_group(self, parent):
        group = SettingCardGroup("Logging", parent)

        self.log_to_file_card = SwitchSettingCard(
            FluentIcon.SAVE,
            "Log to file",
            "Write the application log to translator.log.",
            None,
            group,
        )
        self.log_to_file_card.setChecked(
            bool(self.settings_data.get("log_to_file", False))
        )
        self.log_to_file_card.checkedChanged.connect(self._on_log_to_file_changed)
        group.addSettingCard(self.log_to_file_card)

        self.log_level_card = SettingCard(
            FluentIcon.DOCUMENT,
            "Log level",
            "Verbosity of the application log.",
            group,
        )
        self.log_level_combo = ComboBox(self.log_level_card)
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.log_level_combo.addItem(level)
        current_level = str(self.settings_data.get("log_level", "INFO"))
        level_index = self.log_level_combo.findText(current_level)
        if level_index >= 0:
            self.log_level_combo.setCurrentIndex(level_index)
        self.log_level_combo.currentIndexChanged.connect(
            self._on_log_level_changed
        )
        self.log_level_card.hBoxLayout.addWidget(
            self.log_level_combo, 0, Qt.AlignmentFlag.AlignRight
        )
        self.log_level_card.hBoxLayout.addSpacing(16)
        group.addSettingCard(self.log_level_card)
        return group

    def _build_maintenance_group(self, parent):
        group = SettingCardGroup("Maintenance", parent)

        self.clear_cache_card = PushSettingCard(
            "Clear",
            FluentIcon.DELETE,
            "Translation cache",
            "Remove cached translations for the current file.",
            group,
        )
        self.clear_cache_card.clicked.connect(self.cache_clear_requested)
        group.addSettingCard(self.clear_cache_card)
        return group

    def _on_language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        if not code:
            return
        self.settings_data["user_language"] = code
        self.language_changed.emit(code)

    def _on_translation_mode_changed(self, checked: bool) -> None:
        self.settings_data["translation_mode_enabled"] = checked
        self.translation_mode_changed.emit(checked)

    def _on_log_to_file_changed(self, checked: bool) -> None:
        self.settings_data["log_to_file"] = checked
        self.logging_changed.emit()

    def _on_log_level_changed(self, _index: int) -> None:
        self.settings_data["log_level"] = self.log_level_combo.currentText()
        self.logging_changed.emit()

    def _on_auto_save_changed(self, value: int) -> None:
        self.settings_data["auto_save_interval_ms"] = value * 1000
        self.general_settings_changed.emit()

    def _on_api_workers_changed(self, value: int) -> None:
        max_threads = max(1, QThreadPool.globalInstance().maxThreadCount())
        self.settings_data["api_thread_pool_ratio"] = round(value / max_threads, 2)
        self.general_settings_changed.emit()
