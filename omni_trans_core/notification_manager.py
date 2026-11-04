import os
import uuid
import json
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional
from PySide6 import QtCore
from PySide6.QtMultimedia import QMediaPlayer

from . import settings

logger = logging.getLogger('CORE.notification_manager')


class NotificationType(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class NotificationItem:
    id: str
    type: NotificationType
    text: str
    timestamp: float
    button_text: str = ""
    is_read: bool = False
    source: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "text": self.text,
            "timestamp": self.timestamp,
            "button_text": self.button_text,
            "is_read": self.is_read,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NotificationItem":
        return cls(
            id=data["id"],
            type=NotificationType(data["type"]),
            text=data["text"],
            timestamp=data["timestamp"],
            button_text=data.get("button_text", ""),
            is_read=data.get("is_read", False),
            source=data.get("source", ""),
        )

NOTIFICATION_STYLES = {
    NotificationType.INFO: {
        "icon": "ℹ️",
        "auto_hide_ms": 5000,
        "sound": "notification_info.mp3",
    },
    NotificationType.SUCCESS: {
        "icon": "✅",
        "auto_hide_ms": 3000,
        "sound": "notification_success.mp3",
    },
    NotificationType.WARNING: {
        "icon": "⚠️",
        "auto_hide_ms": None,
        "sound": "notification_warning.mp3",
    },
    NotificationType.ERROR: {
        "icon": "❌",
        "auto_hide_ms": None,
        "sound": "notification_error.mp3",
    },
}


class NotificationManager(QtCore.QObject):
    
    notification_added = QtCore.Signal(NotificationItem)
    notification_removed = QtCore.Signal(str)
    unread_count_changed = QtCore.Signal(int)
    history_cleared = QtCore.Signal()
    
    MAX_VISIBLE_TOASTS = 5
    SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "sounds")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[NotificationItem] = []
        self._visible_toasts: list = []
        self._sound_effects: dict[NotificationType, Optional[object]] = {}
        self._callbacks: dict[str, Callable] = {}
        self._init_sound_effects()
        self._load_history()
        
        notif_settings = settings.current_settings.get("notifications", {})
        self.MAX_VISIBLE_TOASTS = notif_settings.get("max_visible_toasts", 5)
    
    def _init_sound_effects(self):
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            for notif_type in NotificationType:
                sound_file = NOTIFICATION_STYLES[notif_type]["sound"]
                sound_path = os.path.join(self.SOUND_DIR, sound_file)

                if os.path.exists(sound_path):
                    audio_output = QAudioOutput(self)
                    volume = settings.current_settings.get("notifications", {}).get("sound_volume", 0.5)
                    audio_output.setVolume(volume)

                    player = QMediaPlayer(self)
                    player.setAudioOutput(audio_output)
                    player.setSource(QUrl.fromLocalFile(sound_path))

                    self._sound_effects[notif_type] = {
                        "player": player,
                        "audio_output": audio_output
                    }
                else:
                    logger.debug(f"Sound file not found: {sound_path}")
                    self._sound_effects[notif_type] = None
        except ImportError:
            logger.warning("QtMultimedia not available, sound notifications disabled.")
            self._sound_effects = {t: None for t in NotificationType}
    
    def show_notification(
        self,
        type: NotificationType,
        text: str,
        button_text: str = "",
        on_click: Optional[Callable] = None,
        source: str = "",
    ) -> str:
        
        if not settings.current_settings.get("notifications", {}).get("enabled", True):
            logger.debug("Notifications are disabled, skipping.")
            return ""
        
        notif_id = str(uuid.uuid4())
        item = NotificationItem(
            id=notif_id,
            type=type,
            text=text,
            timestamp=QtCore.QDateTime.currentSecsSinceEpoch(),
            button_text=button_text,
            source=source,
        )
        
        if on_click is not None:
            self._callbacks[notif_id] = on_click
        self._history.insert(0, item)
        self._cleanup_history()
        self._save_history()
        self._play_sound(type)
        self.notification_added.emit(item)

        return notif_id

    def get_callback(self, notification_id: str) -> Optional[Callable]:
        return self._callbacks.get(notification_id)

    def _cleanup_callback(self, notification_id: str):
        self._callbacks.pop(notification_id, None)
    
    def get_history(self) -> list[NotificationItem]:
        return list(self._history)
    
    def get_unread_history(self) -> list[NotificationItem]:
        return [n for n in self._history if not n.is_read]
    
    def mark_as_read(self, notification_id: str):
        for item in self._history:
            if item.id == notification_id:
                item.is_read = True
                self._save_history()
                self._emit_unread_count_changed()
                break
    
    def mark_all_as_read(self):
        changed = False
        for item in self._history:
            if not item.is_read:
                item.is_read = True
                changed = True
        if changed:
            self._save_history()
            self._emit_unread_count_changed()
    
    def remove_notification(self, notification_id: str):
        self._history = [n for n in self._history if n.id != notification_id]
        self._cleanup_callback(notification_id)
        self._save_history()
        self.notification_removed.emit(notification_id)
        self._emit_unread_count_changed()

    def clear_history(self):
        self._history.clear()
        self._callbacks.clear()
        self._save_history()
        self.history_cleared.emit()
        self._emit_unread_count_changed()
    
    def get_unread_count(self) -> int:
        return sum(1 for n in self._history if not n.is_read)
    
    def _play_sound(self, type: NotificationType):
        if not settings.current_settings.get("notifications", {}).get("sound_enabled", True):
            return

        sound_data = self._sound_effects.get(type)
        if sound_data:
            try:
                player = sound_data["player"]
                if player.playbackState() == QMediaPlayer.PlayingState:
                    player.stop()
                player.play()
            except Exception as e:
                logger.debug(f"Failed to play sound: {e}")
    
    def _save_history(self):
        try:
            history_file = settings.get_notifications_history_path()
            history_dir = os.path.dirname(history_file)
            os.makedirs(history_dir, exist_ok=True)

            data = {
                "version": 1,
                "notifications": [n.to_dict() for n in self._history],
            }

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save notification history: {e}")

    def _load_history(self):
        history_file = settings.get_notifications_history_path()
        if not os.path.exists(history_file):
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._history = [
                NotificationItem.from_dict(n)
                for n in data.get("notifications", [])
            ]
            
            self._cleanup_history()
            
            logger.debug(f"Loaded {len(self._history)} notifications from history.")
        except Exception as e:
            logger.error(f"Failed to load notification history: {e}")
            self._history = []
    
    def _cleanup_history(self):
        max_items = settings.current_settings.get("notifications", {}).get("history_max_items", 100)
        if len(self._history) > max_items:
            self._history = self._history[:max_items]
    
    def _emit_unread_count_changed(self):
        self.unread_count_changed.emit(self.get_unread_count())
    
    def get_style_for_type(self, type: NotificationType) -> dict:
        return NOTIFICATION_STYLES[type]
