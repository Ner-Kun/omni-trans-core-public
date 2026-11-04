import os
import json
import logging
import time
import weakref
from collections.abc import Mapping
from functools import wraps
from PySide6 import QtCore, QtWidgets
from . import settings
from typing import Literal, TypedDict, TypeGuard, TypeAlias, cast, Callable, Any

logger = logging.getLogger('CORE.localization')

LocalizedKey: TypeAlias = str | list[str] | tuple[str, ...] | None
StoredLocalizedKey: TypeAlias = str | tuple[str, ...] | None

class MetadataFile(TypedDict):
    metadata: dict[str, object]

class TranslationFile(TypedDict):
    translations: dict[str, object]

def is_metadata_file(data: object) -> TypeGuard[MetadataFile]:
    return (
        isinstance(data, dict)
        and "metadata" in data
        and isinstance(data["metadata"], dict)
    )


def is_translation_file(data: object) -> TypeGuard[TranslationFile]:
    return (
        isinstance(data, dict)
        and "translations" in data
        and isinstance(data["translations"], dict)
    )


def auto_register(*mappings: tuple) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        original_init = cls.__init__
        original_retranslate = getattr(cls, 'retranslate_ui', None)

        def resolve_target(instance: Any, target_path: str) -> QtCore.QObject | None:
            target: object = instance
            if not target_path:
                return target if isinstance(target, QtCore.QObject) else None
            for path_part in target_path.split("."):
                if isinstance(target, Mapping):
                    target = target.get(path_part)
                else:
                    target = getattr(target, path_part, None)
                if target is None:
                    logger.warning(
                        "Localization target path '%s' not found in %s",
                        target_path,
                        cls.__name__,
                    )
                    return None
            if not isinstance(target, QtCore.QObject):
                logger.warning(
                    "Localization target path '%s' in %s resolved to unsupported type %s",
                    target_path,
                    cls.__name__,
                    type(target).__name__,
                )
                return None
            return target

        @wraps(original_init)
        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            _auto_register_localizations(self)

        def _auto_register_localizations(self: Any) -> None:
            from .localization_manager import loc_man

            for mapping in mappings:
                widget_name: str = ""
                prop: str = ""
                key: LocalizedKey = ""
                format_arg_names: list[str] | None = None
                extra_kwargs: dict[str, object] | None = None

                if len(mapping) == 3:
                    widget_name, prop, key = mapping
                elif len(mapping) == 4:
                    widget_name, prop, key, fourth = mapping
                    if isinstance(fourth, list):
                        format_arg_names = fourth
                    elif isinstance(fourth, dict):
                        extra_kwargs = fourth
                    else:
                        logger.warning(f"Invalid 4th element in mapping: {mapping}")
                        continue
                elif len(mapping) == 5:
                    widget_name, prop, key, format_arg_names, extra_kwargs = mapping
                    if not isinstance(format_arg_names, list) or not isinstance(extra_kwargs, dict):
                        logger.warning(f"Invalid mapping format (5 elements): {mapping}")
                        continue
                else:
                    logger.warning(f"Invalid mapping format: {mapping}")
                    continue
                
                target = resolve_target(self, widget_name)
                if target is None:
                    continue

                format_args: dict[str, object] = {}
                if format_arg_names:
                    for arg_name in format_arg_names:
                        arg_value = getattr(self, arg_name, None)
                        if arg_value is not None:
                            format_args[arg_name] = arg_value
                        else:
                            logger.debug(
                                f"Format argument '{arg_name}' not found in {cls.__name__}"
                            )

                final_args: dict[str, object] | None = None
                if format_args or extra_kwargs:
                    final_args = format_args.copy()
                    if extra_kwargs:
                        final_args.update(extra_kwargs)

                try:
                    loc_man.register(target, prop, key, final_args)
                except Exception as e:
                    logger.error(
                        f"Failed to register localization for {widget_name}.{prop}: {e}"
                    )

        def retranslate_ui(self: Any) -> None:
            _auto_register_localizations(self)
            if original_retranslate:
                original_retranslate(self)

        cls.__init__ = wrapped_init
        cls._auto_register_localizations = _auto_register_localizations
        cls.retranslate_ui = retranslate_ui

        return cls

    return decorator

class LocalizationManager(QtCore.QObject):
    language_changed: QtCore.Signal = QtCore.Signal()
    SOURCE_CODE_LANGUAGE: str = "en"

    _source_data: dict[str, str]
    _target_data: dict[str, str]
    _display_mode: Literal["translated", "key", "original"]
    _registered_widgets: "weakref.WeakKeyDictionary[QtCore.QObject, dict[str, tuple[StoredLocalizedKey, dict[str, object]]]]"
    _i18n_core_dir: str | None
    _i18n_app_dir: str | None
    _current_language: str
    _language_cache: dict[str, dict[str, str]]
    _loaded_languages: set[str]

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._source_data = {}
        self._target_data = {}
        self._display_mode = "translated"
        self._registered_widgets = weakref.WeakKeyDictionary()
        self._translation_dirs: list[str] = []
        self._language_cache = {}
        self._loaded_languages = set()
        self._missing_keys: set[str] = set()
        core_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_core")
        if os.path.isdir(core_dir):
            self._translation_dirs.append(core_dir)
        else:
            logger.error(f"Core i18n directory not found at expected path: {core_dir}")
        self._current_language = settings.current_settings.get(
            "user_language", self.SOURCE_CODE_LANGUAGE
        )
        self._load_language_data(self.SOURCE_CODE_LANGUAGE, is_source=True)
        _ = self.language_changed.connect(self._retranslate_all)
        self.set_language(self._current_language, force=True)

    def add_translation_directory(self, path: str) -> None:
        if os.path.isdir(path) and path not in self._translation_dirs:
            self._translation_dirs.append(path)
            self.clear_cache()
            logger.debug(f"Added translation source directory: {path}")

    def get_current_file_paths(self) -> dict[str, str]:
        paths: dict[str, str] = {}
        for i, directory in enumerate(self._translation_dirs):
            scope = "core" if "i18n_core" in directory else f"app_{i}"

            source_path = os.path.join(directory, f"{self.SOURCE_CODE_LANGUAGE}.json")
            if os.path.exists(source_path):
                paths[f"source_{scope}"] = source_path

            if self._current_language != self.SOURCE_CODE_LANGUAGE:
                target_path = os.path.join(directory, f"{self._current_language}.json")
                if os.path.exists(target_path):
                    paths[f"target_{scope}"] = target_path
        return paths

    def get_available_languages(self) -> list[dict[str, str]]:
        languages: dict[str, str] = {}
        paths_to_scan = self._translation_dirs
        for path in paths_to_scan:
            if not (path and os.path.isdir(path)):
                continue
            for filename in os.listdir(path):
                if not filename.endswith(".json"):
                    continue
                lang_code = os.path.splitext(filename)[0]
                if lang_code in languages:
                    continue
                file_path = os.path.join(path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = cast(dict[str, object], json.load(f))
                    language_name = lang_code.capitalize()
                    if is_metadata_file(data):
                        name = data["metadata"].get("language_name")
                        if isinstance(name, str) and name:
                            language_name = name
                    languages[lang_code] = language_name
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(
                        f"Could not parse {file_path} to get language name: {e}"
                    )
                    languages[lang_code] = lang_code.capitalize()
        return sorted(
            [{"code": code, "name": name} for code, name in languages.items()],
            key=lambda x: x["name"],
        )

    def _load_language_data(self, lang_code: str, is_source: bool) -> None:
        if lang_code in self._loaded_languages and lang_code in self._language_cache:
            data_dict = self._language_cache[lang_code]
            logger.debug(f"Using cached data for language '{lang_code}' ({len(data_dict)} keys)")
        else:
            data_dict = self._load_language_from_disk(lang_code)
            self._language_cache[lang_code] = data_dict
            self._loaded_languages.add(lang_code)
            logger.debug(f"Loaded and cached language '{lang_code}' ({len(data_dict)} keys)")
        
        if is_source:
            self._source_data = data_dict
        else:
            self._target_data = data_dict

    def _load_language_from_disk(self, lang_code: str) -> dict[str, str]:
        data_dict: dict[str, str] = {}

        def load_file(path_to_json: str) -> dict[str, str]:
            if not os.path.exists(path_to_json):
                logger.debug(f"Localization file not found at {path_to_json}.")
                return {}
            try:
                with open(path_to_json, "r", encoding="utf-8") as f:
                    data = cast(dict[str, object], json.load(f))
                    if is_translation_file(data):
                        return {str(k): str(v) for k, v in data["translations"].items()}
                    logger.warning(
                        f"File {path_to_json} is missing the 'translations' key or it's not a dictionary."
                    )
                    return {}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to parse JSON from {path_to_json}: {e}")
                return {}
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred while loading {path_to_json}: {e}"
                )
                return {}

        for directory in self._translation_dirs:
            file_path = os.path.join(directory, f"{lang_code}.json")
            data_dict.update(load_file(file_path))
        
        return data_dict

    def set_language(self, lang_code: str, *, force: bool = False) -> None:
        if lang_code == self._current_language and not force:
            logger.debug("Language '%s' is already active; skipping retranslation.", lang_code)
            return
        logger.debug(f"Setting language to '{lang_code}'.")
        self._current_language = lang_code
        
        if self.SOURCE_CODE_LANGUAGE not in self._loaded_languages:
            self._load_language_data(self.SOURCE_CODE_LANGUAGE, is_source=True)
        elif not self._source_data:
            self._source_data = self._language_cache.get(self.SOURCE_CODE_LANGUAGE, {})
        
        if lang_code == self.SOURCE_CODE_LANGUAGE:
            self._target_data = self._source_data
        else:
            self._load_language_data(lang_code, is_source=False)
        
        self.language_changed.emit()

    def clear_cache(self) -> None:
        self._language_cache.clear()
        self._loaded_languages.clear()
        logger.debug("Language cache cleared")

    def reload_current_language(self) -> None:
        self.clear_cache()
        self._source_data = {}
        self._target_data = {}
        self.set_language(self._current_language, force=True)

    def set_display_mode(self, mode: str) -> None:
        if mode in ["translated", "key", "original"]:
            typed_mode = cast(Literal["translated", "key", "original"], mode)
            if self._display_mode == typed_mode:
                return
            logger.debug(f"Display mode changed to '{typed_mode}'.")
            self._display_mode = typed_mode
            self.language_changed.emit()
        else:
            logger.warning(f"Attempted to set invalid display mode: {mode}")

    def _retranslate_all(self) -> None:
        started_at = time.perf_counter()
        widget_count = 0
        property_count = 0
        property_timings: list[tuple[float, str]] = []
        profile_updates = logger.isEnabledFor(logging.DEBUG)
        for widget, properties in list(self._registered_widgets.items()):
            widget_count += 1
            try:
                for internal_prop_name, (key, kwargs) in properties.items():
                    prop_name = internal_prop_name
                    property_started_at = time.perf_counter() if profile_updates else 0.0
                    self._update_widget_property(widget, prop_name, key, **kwargs)
                    property_count += 1
                    if profile_updates:
                        property_timings.append(
                            (
                                time.perf_counter() - property_started_at,
                                f"{type(widget).__name__}.{prop_name}",
                            )
                        )
            except RuntimeError as e:
                if "already deleted" in str(e):
                    logger.debug("Skipping retranslation for a deleted widget.")
                    continue
                else:
                    raise
        if profile_updates:
            duration_ms = (time.perf_counter() - started_at) * 1000
            slowest_updates = sorted(property_timings, reverse=True)[:5]
            logger.debug(
                "Retranslated %d properties across %d widgets in %.2f ms; slowest=%s",
                property_count,
                widget_count,
                duration_ms,
                [
                    f"{description}: {duration * 1000:.2f} ms"
                    for duration, description in slowest_updates
                ],
            )

    def _format_string(self, text: str, **kwargs: object) -> str:
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError) as e:
                logger.warning(
                    f"Formatting text '{text[:30]}...' failed. Missing or invalid placeholder: {e}"
                )
        return text

    def translate(self, key: str, **kwargs: object) -> str:
        if not isinstance(key, str):
            logger.warning("Localization key must be a string, got %s.", type(key).__name__)
            return f"<{key}>"
        if key not in self._source_data and key not in self._target_data:
            self._track_missing_key(key)
        if self._display_mode == "key":
            return key
        if self._display_mode == "original":
            source_text: str | None = self._source_data.get(key)
            if source_text is not None:
                return self._format_string(source_text, **kwargs)
            return f"<{key}>"
        target_text: str | None = self._target_data.get(key)
        if target_text is not None:
            return self._format_string(target_text, **kwargs)
        source_text_fallback: str | None = self._source_data.get(key)
        if source_text_fallback is not None:
            return self._format_string(source_text_fallback, **kwargs)
        return f"<{key}>"

    def _track_missing_key(self, key: str) -> None:
        if key not in self._missing_keys:
            self._missing_keys.add(key)
            logger.warning("Missing localization key: %s", key)

    def get_missing_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._missing_keys))

    def clear_missing_keys(self) -> None:
        self._missing_keys.clear()

    def dump_registered_properties(
        self, widget: QtCore.QObject
    ) -> dict[str, tuple[StoredLocalizedKey, dict[str, object]]]:
        return {
            prop_name: (key, kwargs.copy())
            for prop_name, (key, kwargs) in self._registered_widgets.get(widget, {}).items()
        }

    @staticmethod
    def _get_bulk_keys(prop_name: str, key: StoredLocalizedKey) -> tuple[str, ...] | None:
        if not isinstance(key, tuple) or not all(isinstance(item, str) for item in key):
            logger.warning("%s requires a list or tuple of string localization keys.", prop_name)
            return None
        return key

    def _update_widget_property(
        self, widget: QtCore.QObject, prop_name: str, key: StoredLocalizedKey, **kwargs: object
    ) -> None:
        if prop_name == "comboKeys":
            keys = self._get_bulk_keys(prop_name, key)
            if keys is None or not isinstance(widget, QtWidgets.QComboBox):
                if keys is not None:
                    logger.warning("comboKeys requires a QComboBox target.")
                return
            current_index = widget.currentIndex()
            current_data = widget.currentData()
            item_data = [widget.itemData(index) for index in range(widget.count())]
            blocker = QtCore.QSignalBlocker(widget)
            widget.clear()
            for index, item_key in enumerate(keys):
                preserved_data = item_data[index] if index < len(item_data) else None
                widget.addItem(self.translate(item_key), preserved_data)
            restored_index = widget.findData(current_data) if current_data is not None else -1
            if restored_index < 0 and 0 <= current_index < widget.count():
                restored_index = current_index
            if restored_index < 0:
                restored_index = 0 if widget.count() else -1
            widget.setCurrentIndex(restored_index)
            del blocker
            return

        if prop_name == "tabKeys":
            keys = self._get_bulk_keys(prop_name, key)
            if keys is None or not isinstance(widget, QtWidgets.QTabWidget):
                if keys is not None:
                    logger.warning("tabKeys requires a QTabWidget target.")
                return
            if len(keys) > widget.count():
                logger.warning(
                    "tabKeys contains %d keys for %d tabs on %s.",
                    len(keys),
                    widget.count(),
                    type(widget).__name__,
                )
            for index, item_key in enumerate(keys[:widget.count()]):
                widget.setTabText(index, self.translate(item_key))
            return

        if prop_name == "horizontalHeaderKeys":
            keys = self._get_bulk_keys(prop_name, key)
            if keys is None or not isinstance(widget, QtWidgets.QTableWidget):
                if keys is not None:
                    logger.warning("horizontalHeaderKeys requires a QTableWidget target.")
                return
            widget.setHorizontalHeaderLabels([self.translate(item_key) for item_key in keys])
            return

        if prop_name == "retranslate":
            if key is not None:
                logger.warning("retranslate requires None as its localization key.")
                return
            retranslate_ui = getattr(widget, "retranslate_ui", None)
            if callable(retranslate_ui):
                retranslate_ui()
            else:
                logger.warning("%s has no callable retranslate_ui().", type(widget).__name__)
            return

        if not isinstance(key, str):
            logger.warning("%s requires a string localization key.", prop_name)
            return
        text = self.translate(key, **kwargs)
        
        setter_name: str = f"set{prop_name[0].upper()}{prop_name[1:]}"
        if hasattr(widget, setter_name):
            getattr(widget, setter_name)(text)
        elif isinstance(widget, QtWidgets.QGroupBox) and prop_name == "title":
            widget.setTitle(text)
        else:
            logger.debug(
                f"Widget {type(widget).__name__} has no property setter '{setter_name}', trying setProperty."
            )
            _ = widget.setProperty(prop_name, text)

    def register(
        self,
        widget: QtCore.QObject,
        prop_name: str,
        key: LocalizedKey,
        format_args: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        stored_key: StoredLocalizedKey = tuple(key) if isinstance(key, list) else key
        final_args: dict[str, object] = format_args.copy() if format_args else {}
        final_args.update(kwargs)
        if widget not in self._registered_widgets:
            self._registered_widgets[widget] = {}
        self._registered_widgets[widget][prop_name] = (stored_key, final_args)
        self._update_widget_property(widget, prop_name, stored_key, **final_args)

loc_man = LocalizationManager()

def translate(key: str, **kwargs: object) -> str:
    return loc_man.translate(key, **kwargs)
