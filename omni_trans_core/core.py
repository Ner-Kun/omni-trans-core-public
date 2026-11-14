import os
import logging
import webbrowser
import random
from PySide6 import QtWidgets, QtCore, QtGui
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarIcon,
    InfoBarPosition,
    MSFluentWindow,
    NavigationItemPosition,
    PushButton,
    RoundMenu,
    StateToolTip,
    TransparentToolButton,
)
from . import settings
from .constants import MAX_RECENT_FILES
from .interfaces import (
    AbstractDataHandler,
    AbstractTab,
    AbstractPromptFormatter,
    AbstractResponseParser,
)
from .localization_manager import LocalizationManager, loc_man, translate
from .cache_manager import CacheManager
from .ui.widgets import NotificationBell
from .ui.theme import apply_theme
from .ui.pages import AboutPage, SettingsPage
from .notification_manager import NotificationManager, NotificationType, NotificationItem
from .ui.dialogs import (
    ConnectionsDialog,
    DonationDialog,
    ModelInspectorDialog,
    ProgressDialog,
    ProxyDialog,
)
from .utils import DebounceTimer
from .response_parser import DefaultResponseParser
from .logger import LoggerManager
from .prompt_profile_manager import PromptProfileManager
from .prompt_profile import PromptProfile
from .donation import DonationConfig, resolve_donation_config
from .ui.prompt_editor_tab import PromptEditorTab
from typing import override


try:
    from .translation_manager import TranslationManager
except ImportError as e:
    logging.getLogger('CORE').error(
        f"Failed to import TranslationManager: {e}. "
        "Translation functionality will not be available."
    )

try:
    from .developer_tools import DeveloperToolsManager # type: ignore
    dev_tools_available = True
except ImportError:
    dev_tools_available = False
    class _DeveloperToolsManagerStub(QtCore.QObject):
        def __init__(self, main_window: QtWidgets.QWidget, localization_manager: LocalizationManager):
            super().__init__(main_window)
        def activate(self) -> None: pass
        def deactivate(self) -> None: pass
        def handle_language_change(self) -> None: pass

logger = logging.getLogger('CORE')

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 850
DEFAULT_AUTOSAVE_INTERVAL_MS = 5000
DEFAULT_DEBOUNCE_INTERVAL_MS = 1000
STATUS_BAR_SHORT_TIMEOUT_MS = 3000
STATUS_BAR_MEDIUM_TIMEOUT_MS = 5000
STATUS_BAR_LONG_TIMEOUT_MS = 7000


class _StatusBarShim:
    """Keep the old showMessage() API, render through InfoBar."""

    def __init__(self, window: "CoreApp") -> None:
        self.window = window

    def showMessage(self, text: str, timeout: int = 0) -> None:
        self.window.show_status(text, timeout)

    def clearMessage(self) -> None:
        pass


class _LoadingShim:
    """Keep the old loading_overlay API, render through StateToolTip."""

    def __init__(self, window: "CoreApp") -> None:
        self.window = window
        self.tip: StateToolTip | None = None

    def start_animation(self, text: str) -> None:
        self.stop_animation()
        self.tip = StateToolTip("Working", text, self.window)
        self.tip.adjustSize()
        self.tip.move(
            max(0, self.window.width() - self.tip.width() - 24),
            max(0, self.window.height() - self.tip.height() - 24),
        )
        self.tip.show()

    def stop_animation(self) -> None:
        if self.tip is not None:
            self.tip.setState(True)
            self.tip.close()
            self.tip = None


class CoreApp(MSFluentWindow):
    logger_manager: LoggerManager
    app_name: str
    app_version: str
    data_handler: AbstractDataHandler
    prompt_formatter: AbstractPromptFormatter
    response_parser: AbstractResponseParser
    user_tabs: list[AbstractTab]
    loaded_tabs: dict[str, AbstractTab]
    thread_pool: QtCore.QThreadPool
    cache_manager: CacheManager
    translation_manager: "TranslationManager"
    recent_files: list[str]
    recent_menu: QtWidgets.QMenu | None
    progress_dialog: ProgressDialog | None
    model_inspector_window: ModelInspectorDialog | None
    auto_save_timer: DebounceTimer
    dev_tools_manager: "DeveloperToolsManager | _DeveloperToolsManagerStub"
    status_bar: _StatusBarShim
    notification_manager: NotificationManager
    notification_bell: NotificationBell
    loading_overlay: _LoadingShim
    prompt_profile_manager: PromptProfileManager
    prompt_editor_tab: PromptEditorTab
    settings_page: SettingsPage
    about_page: AboutPage
    menu_button: TransparentToolButton
    app_menu: RoundMenu
    new_action: QtGui.QAction
    open_action: QtGui.QAction
    save_action: QtGui.QAction
    exit_action: QtGui.QAction
    settings_action: QtGui.QAction
    toggleModelInspectorAction: QtGui.QAction
    about_action: QtGui.QAction
    clear_recent_action: QtGui.QAction
    file_menu: QtWidgets.QMenu
    view_menu: QtWidgets.QMenu
    help_menu: QtWidgets.QMenu

    def __init__(
        self,
        data_handler: AbstractDataHandler,
        tabs: list[AbstractTab],
        prompt_formatter: AbstractPromptFormatter,
        app_name: str,
        app_version: str,
        response_parser: AbstractResponseParser | None = None,
        default_profile: PromptProfile | None = None,
        donation_config: DonationConfig | None = None,
    ):
        super().__init__()
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(FluentIcon.APPLICATION.icon())
        self.setStyleSheet("CoreApp { background-color: #1a1a1e; }")
        app = QtWidgets.QApplication.instance()
        if app:
            apply_theme(app, dev_mode=settings.DEV_MODE_ENABLED)
        # Page switches are instant: animating heavy pages stutters.
        self.stackedWidget.setAnimationEnabled(False)
        self.logger_manager = LoggerManager(settings.current_settings)
        self.logger_manager.configure_logging()
        self.app_name = app_name
        self.app_version = app_version
        self.donation_config = resolve_donation_config(donation_config)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.data_handler = data_handler
        self.prompt_formatter = prompt_formatter
        self.response_parser = response_parser or DefaultResponseParser()
        self.user_tabs = tabs
        self.loaded_tabs = {}
        self.thread_pool = QtCore.QThreadPool()
        self.cache_manager = CacheManager(self.data_handler)
        from .translation_manager import TranslationManager

        self.translation_manager = TranslationManager(
            self, self.prompt_formatter, self.response_parser
        )
        
        # Initialize prompt profile manager and editor tab
        self.prompt_profile_manager = PromptProfileManager(
            default_profile=default_profile
        )
        active_profile_name = settings.current_settings.get("active_prompt_profile", "")
        active_profile = (
            self.prompt_profile_manager.get_profile(active_profile_name)
            if active_profile_name
            else None
        )
        if active_profile is None:
            active_profile = self.prompt_profile_manager.get_default_profile()
        settings.current_settings["active_prompt_profile"] = active_profile.profile_name
        self.prompt_formatter.update_templates(
            system_prompt=active_profile.system_prompt,
            user_prompt=active_profile.user_prompt,
            regen_prompt=active_profile.regen_prompt,
            context_instructions=active_profile.context_instructions,
        )
        
        self.recent_files = settings.current_settings.get("recent_files", [])
        self.recent_menu = None
        self.progress_dialog = None
        self.model_inspector_window = None
        self.auto_save_timer = DebounceTimer(
            self.save_all_changes,
            int(
                settings.current_settings.get(
                    "auto_save_interval_ms", DEFAULT_AUTOSAVE_INTERVAL_MS
                )
            ),
            parent=self,
        )
        self.create_actions()
        self.create_menus()
        self.init_ui()
        if dev_tools_available:
            self.dev_tools_manager = DeveloperToolsManager(self, loc_man)
        else:
            self.dev_tools_manager = _DeveloperToolsManagerStub(self, loc_man)
        self._connect_signals()
        if settings.current_settings.get("translation_mode_enabled", False):
            self.dev_tools_manager.activate()
        # Reset active connection name on startup so user must explicitly select one
        settings.current_settings["active_connection_name"] = None
        self.translation_manager.active_connection_name = None
        self.translation_manager.apply_rpm_settings_effects()

    # ==========================================================================
    # UI Setup
    # ==========================================================================

    def log_initialization_complete(self) -> None:
        logger.info("Omnis Trans Core Initialized.")

    def init_ui(self) -> None:
        self.status_bar = _StatusBarShim(self)
        self.notification_manager = NotificationManager(self)
        self.notification_bell = NotificationBell(self.notification_manager, self)
        self.notification_manager.notification_added.connect(
            self._on_notification_added
        )
        self._add_title_bar_widget(self.notification_bell)
        self.loading_overlay = _LoadingShim(self)
        self._register_static_localizations()
        self._refresh_dynamic_localization()

    @property
    def tab_widget(self) -> QtWidgets.QStackedWidget:
        return self.stackedWidget

    def _add_title_bar_widget(self, widget: QtWidgets.QWidget) -> None:
        layout = self.titleBar.layout()
        if layout is not None:
            layout.insertWidget(max(0, layout.count() - 3), widget)

    def show_status(self, text: str, timeout: int = 0) -> None:
        if not text:
            return
        InfoBar.new(
            InfoBarIcon.INFORMATION,
            "",
            text,
            duration=timeout or STATUS_BAR_SHORT_TIMEOUT_MS,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )


    def get_available_connection_names(self) -> list[str]:
        connections: list[str] = []
        custom_connections = settings.current_settings.get("custom_connections", [])
        if custom_connections:
            custom_names = [
                conn.get("name")
                for conn in sorted(
                    custom_connections, key=lambda x: x.get("name", "").lower()
                )
            ]
            connections.extend(custom_names)
        return list(dict.fromkeys(connections))

    def get_active_connection_name(self) -> str | None:
        return settings.current_settings.get("active_connection_name")

    def get_active_model_full_id(self) -> str | None:
        conn_name = self.get_active_connection_name()
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(conn_name)
        if not active_model_id:
            return None
        conn_profile = next(
            (
                c
                for c in settings.current_settings.get("custom_connections", [])
                if c.get("name") == conn_name
            ),
            None,
        )
        if not conn_profile:
            return None
        provider = conn_profile.get("provider")
        provider_for_litellm = "openai" if provider == "openai_compatible" else provider
        return f"{provider_for_litellm}/{active_model_id}"

    def are_dev_tools_available(self) -> bool:
        return dev_tools_available

    def set_active_connection_name(self, name: str):
        settings.current_settings["active_connection_name"] = name
        self.translation_manager.set_active_connection(name)

    def browse_and_load_file(self):
        if self.translation_manager.active_translation_jobs > 0:
            QtWidgets.QMessageBox.warning(
                self,
                translate("app.warning.operation_in_progress.title"),
                translate("app.warning.operation_in_progress.text"),
            )
            return
        if self.data_handler.is_dirty():
            if not self._confirm_discard_changes():
                logger.debug("User cancelled file loading due to unsaved changes.")
                return
        file_filter = self.data_handler.get_file_filter()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            translate("app.dialog.open_file.title"),
            os.path.expanduser("~"),
            file_filter,
        )
        if path:
            logger.info(f"User selected file to open: {path}")
            self.load_file(path)

    def load_file(self, path: str):
        logger.info(f"Starting to load file: {path}")
        self.translation_manager.reset_state()
        for tab_instance in self.loaded_tabs.values():
            tab_instance.clear_view()
        self.loading_overlay.start_animation(
            translate("app.status.loading_file", filename=os.path.basename(path))
        )
        QtWidgets.QApplication.processEvents()
        self.data_handler.load(path)

    def save_all_changes(self):
        self.auto_save_timer.cancel()
        is_data_dirty = self.data_handler.is_dirty()
        is_cache_dirty = self.cache_manager.is_dirty()
        if not is_data_dirty and not is_cache_dirty:
            self.status_bar.showMessage(
                translate("app.status.no_changes_to_save"), STATUS_BAR_SHORT_TIMEOUT_MS
            )
            logger.debug(
                "save_all_changes called, but no components are dirty. No action taken."
            )
            return
        logger.debug("Calling on_before_save() for all loaded tabs.")
        for tab_name, tab_instance in self.loaded_tabs.items():
            try:
                tab_instance.on_before_save()
            except Exception as e:
                logger.error(
                    f"Error in on_before_save for tab '{tab_name}': {e}", exc_info=True
                )
        self.loading_overlay.start_animation(translate("app.status.saving_changes"))
        QtWidgets.QApplication.processEvents()
        try:
            if is_cache_dirty:
                self.cache_manager.save_cache()
            if is_data_dirty:
                self.data_handler.save()
            if is_cache_dirty:
                self.cache_manager.set_dirty_flag(False)
            self.status_bar.showMessage(
                translate("app.status.all_changes_saved"), STATUS_BAR_SHORT_TIMEOUT_MS
            )
            logger.info("Data and/or cache saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save changes via data_handler: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self,
                translate("app.dialog.save_error.title"),
                translate("app.dialog.save_error.text", error=e),
            )
            self.status_bar.showMessage(
                translate("app.status.save_failed"), STATUS_BAR_MEDIUM_TIMEOUT_MS
            )
        finally:
            self.loading_overlay.stop_animation()

    def _confirm_discard_changes(self) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(translate("app.dialog.unsaved_changes.title"))
        msg_box.setText(translate("app.dialog.unsaved_changes.text"))
        msg_box.setInformativeText(
            translate("app.dialog.unsaved_changes.informative_text")
        )
        msg_box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Save)
        reply = msg_box.exec()
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            logger.debug("User chose to cancel the operation with unsaved changes.")
            return False
        elif reply == QtWidgets.QMessageBox.StandardButton.Save:
            logger.debug("User chose to save unsaved changes.")
            self.save_all_changes()
        else:
            logger.debug("User chose to discard unsaved changes.")
        return True

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        logger.info("Close event received.")
        if self.translation_manager.active_translation_jobs > 0:
            reply = QtWidgets.QMessageBox.question(
                self,
                translate("app.dialog.confirm_exit.title"),
                translate(
                    "app.dialog.confirm_exit.text",
                    job_count=self.translation_manager.active_translation_jobs,
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                logger.info("Exit cancelled by user due to active jobs.")
                event.ignore()
                return
        if self.data_handler.is_dirty():
            if not self._confirm_discard_changes():
                event.ignore()
                return
        self.translation_manager.cancel_batch_translation(silent=True)
        models_dev_cache_path = settings.MODELS_DEV_CACHE_FILE
        if os.path.exists(models_dev_cache_path):
            try:
                os.remove(models_dev_cache_path)
                logger.debug(
                    f"Removed temporary models.dev cache: {models_dev_cache_path}"
                )
            except OSError as e:
                logger.error(f"Failed to remove temporary models.dev cache: {e}")
        settings.save_settings()
        self.logger_manager.save_log_to_file(settings.LOG_FILE)
        logger.info("Settings and cache saved. Application closing.")
        if self.model_inspector_window:
            self.model_inspector_window.close()
        self.dev_tools_manager.deactivate()
        event.accept()

    def _trigger_ui_update(self):
        QtCore.QCoreApplication.postEvent(self, QtCore.QEvent(QtCore.QEvent.LanguageChange))

    @override
    def changeEvent(self, event: QtCore.QEvent):
        if event.type() == QtCore.QEvent.LanguageChange:
            self._refresh_dynamic_localization()
        super().changeEvent(event)

    def load_user_tabs(self):
        self.prompt_editor_tab = PromptEditorTab(self, self.prompt_profile_manager)
        self.prompt_editor_tab.templates_updated.connect(
            self._on_prompt_templates_updated
        )
        self._add_page(
            self.prompt_editor_tab,
            FluentIcon.DOCUMENT,
            self.prompt_editor_tab.tab_name,
        )
        logger.debug("Prompt Editor page loaded.")

        if not self.user_tabs:
            logger.warning("No tabs provided to CoreApp.")
        else:
            for tab_instance in self.user_tabs:
                title = getattr(tab_instance, "tab_name", None) or getattr(
                    tab_instance, "TAB_NAME", "Unnamed Tab"
                )
                self._add_page(tab_instance, self._icon_for_tab(tab_instance), title)
                logger.debug(f"Page loaded: '{title}'.")
                if hasattr(tab_instance, "translation_requested"):
                    tab_instance.translation_requested.connect(
                        self._on_translation_requested
                    )
                if hasattr(tab_instance, "generation_params_updated"):
                    tab_instance.generation_params_updated.connect(
                        self._on_generation_params_updated
                    )

        self._add_system_pages()

    def _add_page(self, page: QtWidgets.QWidget, icon, title: str) -> None:
        if not page.objectName():
            page.setObjectName(f"page_{len(self.loaded_tabs)}")
        self.addSubInterface(page, icon, title)
        self.loaded_tabs[title] = page

    @staticmethod
    def _icon_for_tab(tab: QtWidgets.QWidget):
        name = getattr(tab, "TAB_NAME", "")
        return {
            "Translation": FluentIcon.LANGUAGE,
            "Editor": FluentIcon.EDIT,
        }.get(name, FluentIcon.DOCUMENT)

    def _add_system_pages(self) -> None:
        self.settings_page = SettingsPage(
            settings.current_settings,
            loc_man.get_available_languages(),
            dev_tools_available,
            self,
        )
        self.settings_page.setObjectName("settingsPage")
        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "Settings",
            position=NavigationItemPosition.BOTTOM,
        )
        self.settings_page.language_changed.connect(self._on_language_changed)
        self.settings_page.logging_changed.connect(self._on_logging_changed)
        self.settings_page.general_settings_changed.connect(
            self._on_general_settings_changed
        )
        self.settings_page.connections_requested.connect(
            self._open_connections_dialog
        )
        self.settings_page.proxy_requested.connect(self._open_proxy_dialog)
        self.settings_page.cache_clear_requested.connect(
            self.cache_manager.clear_cache
        )
        self.settings_page.translation_mode_changed.connect(
            self._on_translation_mode_changed
        )

        self.about_page = AboutPage(
            self.app_name, self.app_version, self.donation_config, self
        )
        self.about_page.setObjectName("aboutPage")
        self.addSubInterface(
            self.about_page,
            FluentIcon.INFO,
            "About",
            position=NavigationItemPosition.BOTTOM,
        )

    def _on_language_changed(self, code: str) -> None:
        loc_man.set_language(code)
        settings.save_settings()
        self._notify_tabs_settings_changed()

    def _on_logging_changed(self) -> None:
        self.logger_manager.configure_logging()
        settings.save_settings()
        self._notify_tabs_settings_changed()

    def _on_general_settings_changed(self) -> None:
        interval = int(
            settings.current_settings.get(
                "auto_save_interval_ms", DEFAULT_AUTOSAVE_INTERVAL_MS
            )
        )
        old_timer = self.auto_save_timer
        self.auto_save_timer = DebounceTimer(
            self.save_all_changes, interval, parent=self
        )
        old_timer.deleteLater()
        self.translation_manager.refresh_api_job_limit()
        settings.save_settings()
        self._notify_tabs_settings_changed()

    def _on_translation_mode_changed(self, enabled: bool) -> None:
        if enabled:
            self.dev_tools_manager.activate()
        else:
            self.dev_tools_manager.deactivate()
            loc_man.set_display_mode("translated")
        settings.save_settings()
        self._notify_tabs_settings_changed()

    def _open_connections_dialog(self) -> None:
        if ConnectionsDialog(self).exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.translation_manager.apply_rpm_settings_effects()
            self._notify_tabs_settings_changed()

    def _open_proxy_dialog(self) -> None:
        if ProxyDialog(self).exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._notify_tabs_settings_changed()

    @QtCore.Slot(str, str, dict)
    def _on_generation_params_updated(self, conn_name: str, model_name: str, params: dict):
        logger.debug(f"_on_generation_params_updated called: conn={conn_name}, model={model_name}, temp={params.get('temperature')}, max_tokens={params.get('max_output_tokens')}")
        if not conn_name:
            logger.debug("_on_generation_params_updated: conn_name is empty, returning")
            return
        custom_connections = settings.current_settings.get("custom_connections", [])
        logger.debug(f"Searching through {len(custom_connections)} custom connections...")
        for conn in custom_connections:
            if conn.get("name") == conn_name:
                if model_name:
                    configured_models = conn.get("configured_models", [])
                    logger.debug(f"Found connection '{conn_name}', searching {len(configured_models)} models for '{model_name}'...")
                    for model_config in configured_models:
                        full_model_id = model_config.get("model_id", "")
                        clean_name = full_model_id.split('/')[-1] if '/' in full_model_id else full_model_id
                        logger.debug(f"Checking model: full_id={full_model_id}, clean_name={clean_name}")
                        if clean_name == model_name or full_model_id == model_name:
                            if "generation_params" not in model_config:
                                model_config["generation_params"] = (
                                    settings.get_default_generation_params()
                                )
                            model_config["generation_params"].update(params)
                            logger.debug(
                                f"SUCCESS: Updated generation params for model '{model_name}' in connection: {conn_name}"
                            )
                            break
                    else:
                        logger.debug(f"Model '{model_name}' NOT FOUND in configured_models, falling back to connection-level params")
                        if "generation_params" not in conn:
                            conn["generation_params"] = (
                                settings.get_default_generation_params()
                            )
                        conn["generation_params"].update(params)
                        logger.debug(
                            f"Model '{model_name}' not found, updated connection-level params for: {conn_name}"
                        )
                else:
                    logger.debug("No model_name specified, saving to connection-level params")
                    if "generation_params" not in conn:
                        conn["generation_params"] = (
                            settings.get_default_generation_params()
                        )
                    conn["generation_params"].update(params)
                    logger.debug(
                        f"Updated generation params for connection: {conn_name}"
                    )
                break
        else:
            logger.debug(f"Connection '{conn_name}' NOT FOUND in custom_connections")
        logger.debug("Calling settings.save_settings()...")
        settings.save_settings()
        logger.debug("settings.save_settings() completed")

    @QtCore.Slot(dict)
    def _on_prompt_templates_updated(self, templates: dict):
        """Handle prompt templates update from PromptEditorTab."""
        self.prompt_formatter.update_templates(
            system_prompt=templates.get('system_prompt', ''),
            user_prompt=templates.get('user_prompt', ''),
            regen_prompt=templates.get('regen_prompt', ''),
            context_instructions=templates.get('context_instructions', ''),
        )
        logger.info("Prompt templates updated from editor.")

    def _register_static_localizations(self):
        loc_man.register(
            self,
            "windowTitle",
            "app.title",
            app_name=self.app_name,
            app_version=self.app_version,
        )
        loc_man.register(self.file_menu, "title", "menu.file")
        loc_man.register(self.recent_menu, "title", "menu.open_recent")
        loc_man.register(self.menu_button, "toolTip", "menu.file")
        loc_man.register(self.new_action, "text", "action.new")
        loc_man.register(self.open_action, "text", "action.open")
        loc_man.register(self.save_action, "text", "action.save")
        loc_man.register(self.exit_action, "text", "action.exit")
        loc_man.register(self.settings_action, "text", "action.settings")
        loc_man.register(
            self.toggleModelInspectorAction, "text", "action.model_inspector"
        )
        loc_man.register(self.toggleModelInspectorAction, "statusTip", "action.model_inspector.tooltip",)
        loc_man.register(self.about_action, "text", "action.about")
        loc_man.register(self.clear_recent_action, "text", "action.clear_recent")

    def _refresh_dynamic_localization(self):
        pass

    def create_actions(self):
        self.new_action = QtGui.QAction(self)
        self.new_action.setShortcut(QtGui.QKeySequence.New)
        self.open_action = QtGui.QAction(self)
        self.open_action.setShortcut(QtGui.QKeySequence.Open)
        self.save_action = QtGui.QAction(self)
        self.save_action.setShortcut(QtGui.QKeySequence.Save)
        self.save_action.setEnabled(False)
        self.exit_action = QtGui.QAction(self)
        self.exit_action.setShortcut(QtGui.QKeySequence.Quit)
        self.settings_action = QtGui.QAction(self)
        self.toggleModelInspectorAction = QtGui.QAction(self, checkable=True)
        self.about_action = QtGui.QAction(self)
        self.clear_recent_action = QtGui.QAction(self)

    def create_menus(self):
        self.app_menu = RoundMenu(parent=self)
        self.app_menu.addAction(self.new_action)
        self.app_menu.addAction(self.open_action)
        self.recent_menu = RoundMenu("Open recent", self)
        self.app_menu.addMenu(self.recent_menu)
        self._update_recent_files_menu()
        self.app_menu.addSeparator()
        self.app_menu.addAction(self.save_action)
        self.app_menu.addSeparator()
        self.app_menu.addAction(self.settings_action)
        self.app_menu.addAction(self.toggleModelInspectorAction)
        self.app_menu.addAction(self.about_action)
        self.app_menu.addSeparator()
        self.app_menu.addAction(self.exit_action)

        self.menu_button = TransparentToolButton(FluentIcon.MENU, self)
        self.menu_button.clicked.connect(self._show_app_menu)
        self._add_title_bar_widget(self.menu_button)
        self.file_menu = self.app_menu
        self.view_menu = self.app_menu
        self.help_menu = self.app_menu

    def add_app_action(
        self, action: QtGui.QAction, before: QtGui.QAction | None = None
    ) -> None:
        """Insert an application action into the File menu."""
        self.file_menu.insertAction(before or self.settings_action, action)

    def _show_app_menu(self) -> None:
        pos = self.menu_button.mapToGlobal(
            QtCore.QPoint(0, self.menu_button.height())
        )
        self.app_menu.exec(pos)

    def show_app_tab(self, tab: QtWidgets.QWidget) -> None:
        """Switch to a page without exposing the navigation widgets."""
        if self.stackedWidget.indexOf(tab) >= 0:
            self.switchTo(tab)

    def _update_recent_files(self, new_path: str):
        if not new_path:
            return
        if new_path in self.recent_files:
            self.recent_files.remove(new_path)
        self.recent_files.insert(0, new_path)
        self.recent_files = self.recent_files[: MAX_RECENT_FILES]
        settings.current_settings["recent_files"] = self.recent_files
        settings.save_settings()
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        if not self.recent_menu:
            return
        self.recent_menu.clear()
        self.recent_files = [
            p
            for p in settings.current_settings.get("recent_files", [])
            if p and os.path.exists(p)
        ]
        settings.current_settings["recent_files"] = self.recent_files
        if not self.recent_files:
            self.recent_menu.setEnabled(False)
            return
        self.recent_menu.setEnabled(True)
        for i, path in enumerate(self.recent_files):
            action = QtGui.QAction(f"&{i + 1}. {os.path.basename(path)}", self)
            action.setData(path)
            action.triggered.connect(self._load_from_recent)
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(self.clear_recent_action)

    @QtCore.Slot()
    def _load_from_recent(self):
        action = self.sender()
        if isinstance(action, QtGui.QAction):
            path = action.data()
            if path and os.path.exists(path):
                self.load_file(path)
            elif path:
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("app.warning.file_not_found.title"),
                    translate("app.warning.file_not_found.text", path=path),
                )
                self._update_recent_files_menu()

    @QtCore.Slot(list, bool)
    def _on_translation_requested(self, items: list, force_regen: bool):
        target_lang = settings.current_settings.get("selected_target_language", "")
        op_name = (
            translate("app.op_name.regenerating")
            if force_regen
            else translate("app.op_name.translating")
        )
        self._start_translation_batch(items, op_name, target_lang, force_regen)

    @QtCore.Slot()
    def _clear_recent_files(self):
        self.recent_files.clear()
        settings.current_settings["recent_files"] = []
        settings.save_settings()
        self._update_recent_files_menu()

    @QtCore.Slot(dict)
    def _on_item_translated(self, update_data: dict):
        logger.debug(f"Received update_data: {update_data}")
        item_id = update_data.get("item_id")
        for tab_name, tab in self.loaded_tabs.items():
            logger.debug(f"Notifying tab: '{tab_name}'")
            if hasattr(tab, "update_item_display"):
                tab.update_item_display(update_data)
            if item_id and hasattr(tab, "flash_items"):
                tab.flash_items([item_id])

    def _connect_signals(self):
        loc_man.language_changed.connect(self._refresh_dynamic_localization)
        loc_man.language_changed.connect(self.dev_tools_manager.handle_language_change)
        
        self.data_handler.data_loaded.connect(self._on_data_loaded)
        self.data_handler.dirty_state_changed.connect(self._on_data_handler_dirty_state_changed)
        
        self.cache_manager.cache_dirty_state_changed.connect(self._on_cache_manager_dirty_state_changed)
        
        self.translation_manager.batch_progress_updated.connect(self._update_progress_dialog)
        self.translation_manager.batch_finished.connect(self._finalize_batch_translation)
        self.translation_manager.item_translated.connect(self._on_item_translated)
        self.translation_manager.model_capability_discovered.connect(self._on_model_capability_discovered)
        self.translation_manager.thinking_misconfigured.connect(self._show_thinking_misconfigured_banner)
        self.translation_manager.thinking_unexpected.connect(self._show_thinking_unexpected_banner)
        self.translation_manager.connection_auto_disabled.connect(self._on_connection_auto_disabled)
        
        self.open_action.triggered.connect(self.browse_and_load_file)
        self.save_action.triggered.connect(self.save_all_changes)
        self.exit_action.triggered.connect(self.close)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        self.toggleModelInspectorAction.triggered.connect(self.toggle_model_inspector)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.clear_recent_action.triggered.connect(self._clear_recent_files)

    @QtCore.Slot(str, str)
    def _on_model_capability_discovered(self, model_id: str, capability: str):
        logger.debug(
            f"[_on_model_capability_discovered] Received for model '{model_id}': {capability}"
        )
        current_tab = self.stackedWidget.currentWidget()
        if hasattr(current_tab, "handle_model_capability_notice"):
            logger.debug("[_on_model_capability_discovered] Forwarding to current tab.")
            current_tab.handle_model_capability_notice(model_id, capability)

    def open_settings_dialog(self):
        self.switchTo(self.settings_page)

    def _notify_tabs_settings_changed(self) -> None:
        for tab in self.loaded_tabs.values():
            if hasattr(tab, "on_settings_changed") and callable(
                getattr(tab, "on_settings_changed")
            ):
                try:
                    tab.on_settings_changed()
                except Exception as exc:
                    logger.error(
                        "Error calling on_settings_changed for tab '%s': %s",
                        getattr(tab, "TAB_NAME", "?"),
                        exc,
                    )

    def show_about_dialog(self):
        self.switchTo(self.about_page)

    def toggle_model_inspector(self):
        if not self.model_inspector_window:
            self.model_inspector_window = ModelInspectorDialog(self)
            self.translation_manager.inspector_update.connect(
                self.model_inspector_window.update_data
            )
        if self.model_inspector_window.isVisible():
            self.model_inspector_window.hide()
        else:
            self.model_inspector_window.show()

    @QtCore.Slot()
    def _on_data_loaded(self):
        self.loading_overlay.stop_animation()
        self.save_action.setEnabled(True)
        self.cache_manager.load_cache()
        for tab_name, tab_instance in self.loaded_tabs.items():
            if hasattr(tab_instance, "on_data_loaded"):
                try:
                    tab_instance.on_data_loaded()
                    logger.debug(f"Called on_data_loaded() for tab '{tab_name}'.")
                except Exception as e:
                    logger.error(
                        f"Error calling on_data_loaded() for tab '{tab_name}': {e}"
                    )
        project_name = self.data_handler.get_project_name()
        self._update_recent_files(self.data_handler.get_project_path())
        self.setWindowTitle(f"{self.app_name} v{self.app_version} - {project_name}")
        self.status_bar.showMessage(
            translate("app.status.loaded_project", project_name=project_name)
        )
        self.data_handler.set_dirty_flag(False)

    @QtCore.Slot(bool)
    def _on_data_handler_dirty_state_changed(self):
        self._update_dirty_state()

    @QtCore.Slot(bool)
    def _on_cache_manager_dirty_state_changed(self):
        self._update_dirty_state()

    def _update_dirty_state(self):
        is_app_dirty = self.data_handler.is_dirty() or self.cache_manager.is_dirty()
        self.save_action.setEnabled(is_app_dirty)
        title = self.windowTitle()
        if is_app_dirty:
            if not title.endswith("*"):
                self.setWindowTitle(f"{title}*")
            self.auto_save_timer.trigger()
        else:
            if title.endswith("*"):
                self.setWindowTitle(title[:-1])
            self.auto_save_timer.cancel()

    def _start_translation_batch(
        self, jobs_to_queue, op_name="Translating", target_lang="", force_regen=False
    ):
        queued_job_count = self.translation_manager.start_translation_batch(
            jobs_to_queue, op_name, target_lang, force_regen
        )
        if queued_job_count > 0:
            if self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog.deleteLater()
            label_text = translate(
                "app.progress_dialog.label",
                op_name=op_name,
                job_count=queued_job_count,
                target_lang=target_lang,
            )
            title_text = translate("app.progress_dialog.title", op_name=op_name)
            self.progress_dialog = ProgressDialog(
                title=title_text, label_text=label_text, parent=self
            )
            self.progress_dialog.set_maximum(queued_job_count)
            self.progress_dialog.set_button_text(
                translate("app.progress_dialog.cancel_button")
            )
            self.progress_dialog.cancel_clicked.connect(
                self.translation_manager.cancel_batch_translation
            )
            self.progress_dialog.show()

    def _update_progress_dialog(self, completed_count, total_count):
        if self.progress_dialog:
            if self.progress_dialog.maximum() != total_count:
                self.progress_dialog.set_maximum(total_count)
            self.progress_dialog.set_value(completed_count)

    def _primary_donation_url(self) -> str:
        target = self.donation_config.app or self.donation_config.core
        return target.url if target else ""

    def _finalize_batch_translation(self, reason: str = ""):
        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None
        completed = self.translation_manager.completed_jobs_for_progress
        total = self.translation_manager.total_jobs_for_progress
        status_msg = translate(
            "app.status.batch_finished", reason=reason, completed=completed, total=total
        )
        log_msg = f"Batch {reason}. Processed {completed}/{total}."
        if "cancel" in reason or "stop" in reason:
            cancelled_count = (
                total - self.translation_manager.completed_jobs_for_progress
            )
            if cancelled_count > 0:
                cancelled_msg_ui = translate(
                    "app.status.batch_cancelled_pending", count=cancelled_count
                )
                status_msg += f" {cancelled_msg_ui}"
                log_msg += f" {cancelled_count} pending cancelled."
        self.status_bar.showMessage(status_msg, STATUS_BAR_LONG_TIMEOUT_MS)
        logger.info(log_msg)
        translation_count = int(settings.current_settings.get("ux_t_count", 0))
        next_prompt_at = int(settings.current_settings.get("ux_next_prompt", 250))
        if translation_count >= next_prompt_at:
            is_dialog_shown_before = settings.current_settings.get(
                "ux_dialog_shown", False
            )
            if not is_dialog_shown_before:
                dialog = DonationDialog(self, self.donation_config)
                dialog.exec()
                settings.current_settings["ux_dialog_shown"] = True
            else:
                self.notification_manager.show_notification(
                    type=NotificationType.INFO,
                    text=translate("notification.donation.text"),
                    button_text=translate("notification.donation.button"),
                    on_click=lambda: webbrowser.open(self._primary_donation_url()),
                )
            new_next_prompt_at = translation_count + 500 + random.randint(-150, 150)
            settings.current_settings["ux_next_prompt"] = new_next_prompt_at
            logger.debug(
                f"Donation prompt triggered. Next prompt will be at ~{new_next_prompt_at} translations."
            )

    @QtCore.Slot(str)
    def _open_connection_settings(self, connection_name: str):
        from .ui.dialogs import ProviderConfigDialog

        profile = next(
            (
                c
                for c in settings.current_settings.get("custom_connections", [])
                if c.get("name") == connection_name
            ),
            None,
        )
        if not profile:
            logger.warning(
                f"Could not find connection profile for '{connection_name}' to open settings."
            )
            return
        dialog = ProviderConfigDialog(existing_config=profile, parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updated_data = dialog.get_data()
            if updated_data:
                custom_connections = settings.current_settings.get(
                    "custom_connections", []
                )
                for i, conn in enumerate(custom_connections):
                    if conn.get("id") == updated_data.get("id"):
                        custom_connections[i] = updated_data
                        break
                settings.save_settings()
                for tab in self.loaded_tabs.values():
                    if hasattr(tab, "on_settings_changed"):
                        tab.on_settings_changed()
                logger.info(
                    f"Connection '{connection_name}' updated via banner dialog."
                )

    @QtCore.Slot(str, str)
    def _show_thinking_misconfigured_banner(self, conn_name: str, model_name: str):
        text = translate(
            "notification.thinking_misconfigured.text",
            conn_name=conn_name,
            model_name=model_name,
        )
        button_text = translate("notification.thinking_misconfigured.button")

        def on_click():
            return self._open_connection_settings(conn_name)

        self.notification_manager.show_notification(
            type=NotificationType.WARNING,
            text=text,
            button_text=button_text,
            on_click=on_click,
        )

    @QtCore.Slot(str, str)
    def _show_thinking_unexpected_banner(self, conn_name: str, model_name: str):
        text = translate(
            "notification.thinking_unexpected.text",
            conn_name=conn_name,
            model_name=model_name,
        )
        self.notification_manager.show_notification(
            type=NotificationType.WARNING,
            text=text,
        )

    @QtCore.Slot(str)
    def _on_connection_auto_disabled(self, connection_name: str):
        text = translate(
            "notification.connection_auto_disabled.text",
            connection_name=connection_name,
        )
        button_text = translate("notification.connection_auto_disabled.button")
        self.notification_manager.show_notification(
            type=NotificationType.WARNING,
            text=text,
            button_text=button_text,
            on_click=lambda: None,
        )

    @QtCore.Slot(NotificationItem)
    def _on_notification_added(self, notification: NotificationItem):
        icon_map = {
            NotificationType.INFO: InfoBarIcon.INFORMATION,
            NotificationType.SUCCESS: InfoBarIcon.SUCCESS,
            NotificationType.WARNING: InfoBarIcon.WARNING,
            NotificationType.ERROR: InfoBarIcon.ERROR,
        }
        icon = icon_map.get(notification.type, InfoBarIcon.INFORMATION)
        bar = InfoBar.new(
            icon,
            "",
            notification.text,
            duration=5000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )
        callback = self.notification_manager.get_callback(notification.id)
        if notification.button_text and callback:
            button = PushButton(notification.button_text, bar)
            button.clicked.connect(callback)
            bar.addWidget(button)
