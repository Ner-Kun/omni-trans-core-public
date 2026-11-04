"""
Prompt Editor Tab - UI for editing prompt profiles.
"""
import logging
import re
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui
from omni_trans_core.interfaces import AbstractTab
from omni_trans_core.prompt_profile import PromptProfile, DEFAULT_PLACEHOLDERS
from omni_trans_core.prompt_profile_manager import PromptProfileManager
from omni_trans_core.localization_manager import auto_register, translate

logger = logging.getLogger('CORE.ui.prompt_editor_tab')

# Placeholder pattern for highlighting
PLACEHOLDER_PATTERN = re.compile(r'\{(\w+)\}')


@auto_register(
    ("title_label", "text", "prompt_editor.placeholders"),
)
class PlaceholderListWidget(QtWidgets.QWidget):
    """Widget displaying list of available placeholders with copy functionality."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # Placeholder list
        self.placeholder_list = QtWidgets.QListWidget()
        self.placeholder_list.setSpacing(2)
        layout.addWidget(self.placeholder_list)
        
        # Add placeholders
        for placeholder, description in DEFAULT_PLACEHOLDERS:
            item = QtWidgets.QListWidgetItem()
            self.placeholder_list.addItem(item)
            
            widget = PlaceholderItemWidget(placeholder, description)
            item.setSizeHint(widget.sizeHint())
            self.placeholder_list.setItemWidget(item, widget)
    
    def update_placeholders(self, used_placeholders: set[str]):
        """Update the list to show which placeholders are used."""
        for i in range(self.placeholder_list.count()):
            item = self.placeholder_list.item(i)
            widget = self.placeholder_list.itemWidget(item)
            if widget:
                widget.set_used(widget.placeholder in used_placeholders)


@auto_register(
    ("copy_btn", "toolTip", "prompt_editor.copied"),
)
class PlaceholderItemWidget(QtWidgets.QWidget):
    """Single placeholder item with copy button."""
    
    def __init__(self, placeholder: str, description: str, parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self._init_ui(placeholder, description)
    
    def _init_ui(self, placeholder: str, description: str):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        
        # Status indicator
        self.status_label = QtWidgets.QLabel("○")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.status_label)
        
        # Placeholder text
        placeholder_label = QtWidgets.QLabel(placeholder)
        placeholder_label.setStyleSheet("font-family: monospace; color: #4a9eff;")
        placeholder_label.setMinimumWidth(160)
        layout.addWidget(placeholder_label)
        
        # Copy button
        self.copy_btn = QtWidgets.QPushButton("📋")
        self.copy_btn.setFixedSize(24, 24)
        layout.addWidget(self.copy_btn)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        
        # Used indicator
        self.used_indicator = QtWidgets.QLabel("")
        layout.addWidget(self.used_indicator)
    
    def _copy_to_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.placeholder)
    
    def set_used(self, used: bool):
        """Set whether this placeholder is used in current prompts."""
        if used:
            self.status_label.setText("✓")
            self.status_label.setStyleSheet("color: #4caf50; font-size: 10px;")
            self.used_indicator.setText("✓")
            self.used_indicator.setStyleSheet("color: #4caf50;")
        else:
            self.status_label.setText("○")
            self.status_label.setStyleSheet("color: #888; font-size: 10px;")
            self.used_indicator.setText("")
            self.used_indicator.setStyleSheet("")


@auto_register(
    ("title_label", "text", "prompt_editor.validation"),
)
class ValidationPanel(QtWidgets.QWidget):
    """Panel showing validation results for placeholders."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # Status label
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
    
    def update_validation(self, missing_placeholders: dict[str, list[str]]):
        """Update validation display."""
        if not missing_placeholders:
            self.status_label.setText("✓ " + translate("prompt_editor.validation.all_required_found"))
            self.status_label.setStyleSheet("color: #4caf50;")
        else:
            messages = []
            for prompt_type, missing in missing_placeholders.items():
                messages.append(f"• {prompt_type}: missing {', '.join(missing)}")
            self.status_label.setText("❌ " + "\n".join(messages))
            self.status_label.setStyleSheet("color: #f44336;")


@auto_register(
    ("title_label", "text", "prompt_editor.preview"),
    ("_src_label", "text", "prompt_editor.preview.source_lang"),
    ("_tgt_label", "text", "prompt_editor.preview.target_lang"),
    ("_kw_label", "text", "prompt_editor.preview.keyword"),
    ("keyword_input", "placeholderText", "prompt_editor.preview.placeholder_keyword"),
    ("preview_text", "placeholderText", "prompt_editor.preview.placeholder_output"),
)
class PreviewPanel(QtWidgets.QWidget):
    """Panel showing prompt preview with sample data."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # Input fields
        self._preview_input_layout = QtWidgets.QFormLayout()
        
        self.source_lang_combo = QtWidgets.QComboBox()
        self.source_lang_combo.addItems(["English", "Japanese", "Korean", "Chinese"])
        self._src_label = QtWidgets.QLabel()
        self._preview_input_layout.addRow(self._src_label, self.source_lang_combo)
        
        self.target_lang_combo = QtWidgets.QComboBox()
        self.target_lang_combo.addItems(["Ukrainian", "English", "Russian", "Polish"])
        self._tgt_label = QtWidgets.QLabel()
        self._preview_input_layout.addRow(self._tgt_label, self.target_lang_combo)
        
        self.keyword_input = QtWidgets.QLineEdit()
        self.keyword_input.setText("magic sword")
        self._kw_label = QtWidgets.QLabel()
        self._preview_input_layout.addRow(self._kw_label, self.keyword_input)
        
        layout.addLayout(self._preview_input_layout)
        
        # Preview text
        self.preview_text = QtWidgets.QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        layout.addWidget(self.preview_text)
        
        # Connect signals
        self.source_lang_combo.currentTextChanged.connect(self._update_preview)
        self.target_lang_combo.currentTextChanged.connect(self._update_preview)
        self.keyword_input.textChanged.connect(self._update_preview)
    
    def set_profile(self, profile: PromptProfile):
        """Set the profile for preview."""
        self._profile = profile
        self._update_preview()
    
    def _update_preview(self):
        """Update the preview text."""
        if not hasattr(self, '_profile'):
            return
        
        profile = self._profile
        source = self.source_lang_combo.currentText()
        target = self.target_lang_combo.currentText()
        keyword = self.keyword_input.text() or "keyword"
        
        # Build preview
        preview_lines = [
            "System Prompt",
            profile.system_prompt.format(
                source_language_name=source,
                target_language_name=target,
                context_instructions="[context instructions]",
                context_section="[context content]",
            ),
            "",
            "User Prompt",
            profile.user_prompt.format(
                source_language_name=source,
                target_language_name=target,
                keyword=keyword,
            ),
        ]
        
        self.preview_text.setPlainText("\n".join(preview_lines))


@auto_register(
    ("_profile_label", "text", "prompt_editor.profile_selector"),
    ("btn_load", "text", "prompt_editor.btn_load"),
    ("btn_load", "toolTip", "prompt_editor.btn_load.tooltip"),
    ("btn_save", "text", "prompt_editor.btn_save"),
    ("btn_save", "toolTip", "prompt_editor.btn_save.tooltip"),
    ("btn_save_as", "text", "prompt_editor.btn_save_as"),
    ("btn_save_as", "toolTip", "prompt_editor.btn_save_as.tooltip"),
    ("btn_new", "text", "prompt_editor.btn_new"),
    ("btn_new", "toolTip", "prompt_editor.btn_new.tooltip"),
    ("btn_delete", "text", "prompt_editor.btn_delete"),
    ("btn_delete", "toolTip", "prompt_editor.btn_delete.tooltip"),
    ("prompt_tabs", "tabKeys", (
        "prompt_editor.system_prompt",
        "prompt_editor.user_prompt",
        "prompt_editor.regen_prompt",
        "prompt_editor.context_instructions",
    )),
)
class PromptEditorTab(AbstractTab):
    """Tab for editing prompt profiles."""
    
    TAB_NAME = "Prompt Editor"
    
    # Signals
    profile_changed = QtCore.Signal(str)  # Emitted when active profile changes
    templates_updated = QtCore.Signal(dict)  # Emitted when templates are updated
    
    def __init__(self, main_window, profile_manager: PromptProfileManager):
        super().__init__(main_window)
        logger.debug("Initializing PromptEditorTab")
        self.main_window = main_window
        self.profile_manager = profile_manager
        self.current_profile: Optional[PromptProfile] = None
        self._dirty = False

        self.init_ui()
        self._load_profiles()
        logger.info("PromptEditorTab initialized")
    
    @property
    def tab_name(self) -> str:
        """Localized tab name for display."""
        return translate("prompt_editor.tab_name")
    
    def init_ui(self):
        """Initialize the UI."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QtWidgets.QHBoxLayout()
        
        # Profile selector
        self._profile_label = QtWidgets.QLabel()
        toolbar_layout.addWidget(self._profile_label)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        toolbar_layout.addWidget(self.profile_combo)
        
        # Toolbar buttons
        self.btn_load = QtWidgets.QPushButton()
        self.btn_load.clicked.connect(self._on_load_clicked)
        toolbar_layout.addWidget(self.btn_load)
        
        self.btn_save = QtWidgets.QPushButton()
        self.btn_save.clicked.connect(self._on_save_clicked)
        toolbar_layout.addWidget(self.btn_save)
        
        self.btn_save_as = QtWidgets.QPushButton()
        self.btn_save_as.clicked.connect(self._on_save_as_clicked)
        toolbar_layout.addWidget(self.btn_save_as)
        
        self.btn_new = QtWidgets.QPushButton()
        self.btn_new.clicked.connect(self._on_new_clicked)
        toolbar_layout.addWidget(self.btn_new)
        
        self.btn_delete = QtWidgets.QPushButton()
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        toolbar_layout.addWidget(self.btn_delete)
        
        toolbar_layout.addStretch()
        
        main_layout.addLayout(toolbar_layout)
        
        # Main content splitter
        content_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        content_splitter.setOpaqueResize(False)
        
        # Left panel - prompt editors
        left_panel = self._create_editors_panel()
        content_splitter.addWidget(left_panel)
        
        # Right panel - placeholders, validation, preview
        right_panel = self._create_right_panel()
        content_splitter.addWidget(right_panel)
        
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(content_splitter)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("")
        main_layout.addWidget(self.status_label)
        
    def _create_editors_panel(self) -> QtWidgets.QWidget:
        """Create the prompt editors panel."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab widget for different prompts
        self.prompt_tabs = QtWidgets.QTabWidget()
        
        # System Prompt
        self.system_prompt_editor = self._create_text_editor()
        self.prompt_tabs.addTab(self.system_prompt_editor, "")
        
        # User Prompt
        self.user_prompt_editor = self._create_text_editor()
        self.prompt_tabs.addTab(self.user_prompt_editor, "")
        
        # Regen Prompt
        self.regen_prompt_editor = self._create_text_editor()
        self.prompt_tabs.addTab(self.regen_prompt_editor, "")
        
        # Context Instructions
        self.context_instructions_editor = self._create_text_editor()
        self.prompt_tabs.addTab(self.context_instructions_editor, "")
        
        layout.addWidget(self.prompt_tabs)
        
        return widget
    
    def _create_text_editor(self) -> QtWidgets.QTextEdit:
        """Create a text editor with placeholder highlighting."""
        editor = QtWidgets.QTextEdit()
        editor.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        editor.setFont(QtGui.QFont("Consolas", 10))
        editor.textChanged.connect(self._on_editor_changed)
        return editor
    
    def _create_right_panel(self) -> QtWidgets.QWidget:
        """Create the right panel with placeholders, validation, and preview."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Placeholders
        self.placeholder_widget = PlaceholderListWidget()
        layout.addWidget(self.placeholder_widget)
        
        # Validation
        self.validation_panel = ValidationPanel()
        layout.addWidget(self.validation_panel)
        
        # Preview
        self.preview_panel = PreviewPanel()
        layout.addWidget(self.preview_panel)
        
        layout.addStretch()
        
        return widget
    
    def _load_profiles(self):
        """Load all profiles into the combo box."""
        profiles = self.profile_manager.load_profiles()
        logger.debug("Loaded %d profiles from manager", len(profiles))
        self.profile_combo.clear()

        for profile in profiles:
            self.profile_combo.addItem(profile.profile_name)

        # Select default
        default_profile = self.profile_manager.get_default_profile()
        index = self.profile_combo.findText(default_profile.profile_name)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        logger.info("Profile list populated: %s", [p.profile_name for p in profiles])
    
    def _on_profile_selected(self, profile_name: str):
        """Handle profile selection from combo box."""
        # Don't load immediately - wait for Load button
        pass
    
    def _on_load_clicked(self):
        """Load the selected profile."""
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            logger.warning("Load clicked with empty profile name")
            return

        # Check if already loaded
        if self.current_profile and self.current_profile.profile_name == profile_name:
            logger.debug("Profile '%s' is already loaded", profile_name)
            msg = translate("prompt_editor.status.profile_loaded_already", profile_name=profile_name)
            self._set_status(msg)
            return

        logger.info("Loading profile: %s", profile_name)
        profile = self.profile_manager.get_profile(profile_name)
        if profile:
            self._load_profile(profile)
            logger.debug("Profile '%s' loaded successfully", profile_name)
            msg = translate("prompt_editor.profile_loaded", profile_name=profile_name)
            self._set_status(msg)
        else:
            logger.error("Failed to load profile: %s", profile_name)
            msg = translate("prompt_editor.status.load_failed", profile_name=profile_name)
            self._set_status(msg, error=True)
    
    def _load_profile(self, profile: PromptProfile):
        """Load a profile into the editors."""
        self.current_profile = profile
        
        # Block signals to prevent triggering textChanged
        self.system_prompt_editor.blockSignals(True)
        self.user_prompt_editor.blockSignals(True)
        self.regen_prompt_editor.blockSignals(True)
        self.context_instructions_editor.blockSignals(True)
        
        # Set text
        self.system_prompt_editor.setPlainText(profile.system_prompt)
        self.user_prompt_editor.setPlainText(profile.user_prompt)
        self.regen_prompt_editor.setPlainText(profile.regen_prompt)
        self.context_instructions_editor.setPlainText(profile.context_instructions)
        
        # Unblock signals
        self.system_prompt_editor.blockSignals(False)
        self.user_prompt_editor.blockSignals(False)
        self.regen_prompt_editor.blockSignals(False)
        self.context_instructions_editor.blockSignals(False)
        
        # Update validation and preview
        self._update_validation()
        self._update_preview()
        self._update_placeholder_status()
        
        self._dirty = False
    
    def _on_save_clicked(self):
        """Save the current profile."""
        if not self.current_profile:
            logger.warning("Save clicked without active profile")
            return

        # Update profile from editors
        self._update_profile_from_editors()

        # Save
        profile_name = self.current_profile.profile_name
        logger.info("Saving profile: %s", profile_name)
        if self.profile_manager.save_profile(self.current_profile):
            logger.info("Profile '%s' saved successfully", profile_name)
            msg = translate("prompt_editor.profile_saved", profile_name=profile_name)
            self._set_status(msg)
            self._dirty = False
            self.templates_updated.emit(self._get_current_templates())
        else:
            logger.error("Failed to save profile: %s", profile_name)
            self._set_status(translate("prompt_editor.status.save_failed"), error=True)
    
    def _on_save_as_clicked(self):
        """Save the current profile with a new name."""
        # Get new name from dialog
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle(translate("prompt_editor.dialog.save_as.title"))
        dialog.setLabelText(translate("prompt_editor.dialog.save_as.label"))
        dialog.setTextValue(self.current_profile.profile_name if self.current_profile else "New Profile")

        if dialog.exec():
            new_name = dialog.textValue().strip()
            if not new_name:
                logger.warning("Save As cancelled: empty name provided")
                return

            # Check if exists
            if self.profile_manager.profile_exists(new_name):
                logger.warning("Save As failed: profile '%s' already exists", new_name)
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("prompt_editor.dialog.profile_exists.title"),
                    translate("prompt_editor.dialog.profile_exists", profile_name=new_name),
                )
                return

            # Create new profile
            self._update_profile_from_editors()
            new_profile = self.current_profile.copy() if self.current_profile else PromptProfile()
            new_profile.profile_name = new_name
            new_profile._file_path = None

            logger.info("Saving profile as: %s", new_name)
            if self.profile_manager.save_profile(new_profile):
                logger.info("Profile '%s' saved successfully", new_name)
                self.current_profile = new_profile
                self.profile_combo.addItem(new_name)
                self.profile_combo.setCurrentText(new_name)
                msg = translate("prompt_editor.profile_saved", profile_name=new_name)
                self._set_status(msg)
                self._dirty = False
                self.templates_updated.emit(self._get_current_templates())
            else:
                logger.error("Failed to save profile as: %s", new_name)
    
    def _on_new_clicked(self):
        """Create a new profile."""
        # Get name from dialog
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle(translate("prompt_editor.dialog.new_profile.title"))
        dialog.setLabelText(translate("prompt_editor.dialog.new_profile.label"))
        dialog.setTextValue(translate("prompt_editor.btn_new"))

        if dialog.exec():
            name = dialog.textValue().strip()
            if not name:
                logger.warning("New profile cancelled: empty name provided")
                return

            if self.profile_manager.profile_exists(name):
                logger.warning("New profile failed: profile '%s' already exists", name)
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("prompt_editor.dialog.profile_exists.title"),
                    translate("prompt_editor.dialog.profile_exists", profile_name=name),
                )
                return

            # Create and load new profile
            logger.info("Creating new profile: %s", name)
            new_profile = self.profile_manager.create_profile(name)
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name)
            self._load_profile(new_profile)
            logger.info("Profile '%s' created and loaded", name)
            msg = translate("prompt_editor.dialog.new_profile.created", profile_name=name)
            self._set_status(msg)
    
    def _on_delete_clicked(self):
        """Delete the current profile."""
        if not self.current_profile:
            logger.warning("Delete clicked without active profile")
            return

        profile_name = self.current_profile.profile_name
        logger.warning("User requested deletion of profile: %s", profile_name)

        # Confirm deletion
        reply = QtWidgets.QMessageBox.question(
            self,
            translate("prompt_editor.dialog.delete.title"),
            translate("prompt_editor.dialog.confirm_delete", profile_name=profile_name),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            if self.profile_manager.delete_profile(profile_name):
                logger.info("Profile '%s' deleted", profile_name)
                self.profile_combo.removeItem(self.profile_combo.currentIndex())
                # Load default
                default = self.profile_manager.get_default_profile()
                self.profile_combo.setCurrentText(default.profile_name)
                self._load_profile(default)
                msg = translate("prompt_editor.profile_deleted", profile_name=profile_name)
                self._set_status(msg)
            else:
                logger.error("Failed to delete profile: %s", profile_name)
    
    def _on_editor_changed(self):
        """Handle text changes in editors."""
        self._dirty = True
        self._update_validation()
        self._update_preview()
        self._update_placeholder_status()
    
    def _update_profile_from_editors(self):
        """Update current profile with values from editors."""
        if not self.current_profile:
            return
        
        self.current_profile.system_prompt = self.system_prompt_editor.toPlainText()
        self.current_profile.user_prompt = self.user_prompt_editor.toPlainText()
        self.current_profile.regen_prompt = self.regen_prompt_editor.toPlainText()
        self.current_profile.context_instructions = self.context_instructions_editor.toPlainText()
    
    def _update_validation(self):
        """Update validation panel."""
        if not self.current_profile:
            return

        self._update_profile_from_editors()
        missing = self.current_profile.validate()
        if missing:
            logger.debug("Validation found missing placeholders: %s", missing)
        self.validation_panel.update_validation(missing)
    
    def _update_preview(self):
        """Update preview panel."""
        if not self.current_profile:
            return
        
        self._update_profile_from_editors()
        self.preview_panel.set_profile(self.current_profile)
    
    def _update_placeholder_status(self):
        """Update which placeholders are used."""
        if not self.current_profile:
            return
        
        self._update_profile_from_editors()
        used = set()
        for attr in ['system_prompt', 'user_prompt', 'regen_prompt', 'context_instructions']:
            text = getattr(self.current_profile, attr, '')
            found = PLACEHOLDER_PATTERN.findall(text)
            used.update(f'{{{p}}}' for p in found)
        
        self.placeholder_widget.update_placeholders(used)
    
    def _get_current_templates(self) -> dict:
        """Get current templates from editors."""
        return {
            'system_prompt': self.system_prompt_editor.toPlainText(),
            'user_prompt': self.user_prompt_editor.toPlainText(),
            'regen_prompt': self.regen_prompt_editor.toPlainText(),
            'context_instructions': self.context_instructions_editor.toPlainText(),
        }
    
    def _set_status(self, message: str, error: bool = False):
        """Set status bar message."""
        if error:
            self.status_label.setStyleSheet("color: #f44336;")
        else:
            self.status_label.setStyleSheet("color: #888;")
        self.status_label.setText(message)
    
    def update_entry(self, entry_id: str, new_data: dict):
        """AbstractTab interface - not used."""
        pass
    
    def get_selected_items_for_translation(self) -> list:
        """AbstractTab interface - not used."""
        return []
    
    def flash_items(self, item_ids: list[str]):
        """AbstractTab interface - not used."""
        pass
