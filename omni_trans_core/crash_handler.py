import sys
import traceback
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable


class CrashHandler:
    """Глобальный обработчик крашей с сохранением логов."""
    
    _instance: Optional["CrashHandler"] = None
    _initialized: bool = False
    
    def __init__(
        self,
        crash_logs_dir: Optional[Path] = None,
        app_name: str = "App",
        on_crash_callback: Optional[Callable[[str], None]] = None,
        get_app_log_callback: Optional[Callable[[], str]] = None,
    ):
        """
        Инициализация обработчика крашей.

        Args:
            crash_logs_dir: Директория для сохранения логов крашей
            app_name: Имя приложения для заголовка лога
            on_crash_callback: Опциональный callback при краше
            get_app_log_callback: Callback для получения полного лога приложения
        """
        self.crash_logs_dir = crash_logs_dir or Path.home()
        self.app_name = app_name
        self.on_crash_callback = on_crash_callback
        self.get_app_log_callback = get_app_log_callback

        # Сохраняем оригинальные обработчики
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = getattr(threading, "excepthook", None)
        self._original_qt_message_handler = None
        
    @classmethod
    def get_instance(cls) -> Optional["CrashHandler"]:
        """Получить текущий экземпляр обработчика."""
        return cls._instance
    
    def install(self) -> None:
        """Установить все перехватчики."""
        if self._initialized:
            return
            
        # 1. sys.excepthook - главный поток
        sys.excepthook = self._handle_exception
        
        # 2. threading.excepthook - другие потоки (Python 3.8+)
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._handle_thread_exception
        
        # 3. qInstallMessageHandler - Qt сообщения
        self._install_qt_message_handler()
        
        self._initialized = True
        CrashHandler._instance = self
        
    def _handle_exception(self, exc_type, exc_value, exc_tb) -> None:
        """Обработать исключение в главном потоке."""
        self._save_crash_log(exc_type, exc_value, exc_tb, source="main_thread")
        
        # Вызываем оригинальный обработчик если есть
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_tb)
            
    def _handle_thread_exception(self, args) -> None:
        """Обработать исключение в потоке."""
        # args - threading.ExceptHookArgs (Python 3.8+)
        thread_name = args.thread.name if args.thread else "unknown"
        self._save_crash_log(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            source=f"thread:{thread_name}"
        )
        
        # Вызываем оригинальный обработчик если есть
        if self._original_threading_excepthook:
            self._original_threading_excepthook(args)
            
    def _install_qt_message_handler(self) -> None:
        """Установить обработчик Qt сообщений."""
        try:
            from PySide6.QtCore import qInstallMessageHandler, QtMsgType
            
            def qt_message_handler(msg_type, context, message):
                # Обрабатываем только критические и фатальные сообщения
                if msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                    self._save_qt_error(msg_type, context, message)
                    
            self._original_qt_message_handler = qInstallMessageHandler(qt_message_handler)
            
        except ImportError:
            pass  # Qt не доступен
            
    def _save_qt_error(self, msg_type, context, message: str) -> None:
        """Сохранить Qt ошибку как краш лог."""
        type_name = str(msg_type).split(".")[-1] if msg_type else "Unknown"
        
        # Создаём фиктивный traceback для Qt ошибки
        crash_file = self._save_crash_log_raw(
            title=f"{self.app_name} Qt Error Report",
            source=f"qt:{type_name}",
            content=self._format_qt_error(msg_type, context, message)
        )
        
        print(f"\n{'!' * 60}")
        print(f"Qt {type_name} detected!")
        print(f"Crash log saved: {crash_file}")
        print(f"{'!' * 60}\n")
        
    def _format_qt_error(self, msg_type, context, message: str) -> str:
        """Форматировать Qt ошибку для записи в лог."""
        type_name = str(msg_type).split(".")[-1] if msg_type else "Unknown"
        
        lines = [
            f"Qt Message Type: {type_name}",
            f"Message: {message}",
        ]
        
        if context:
            if hasattr(context, "file") and context.file:
                lines.append(f"File: {context.file}")
            if hasattr(context, "line") and context.line:
                lines.append(f"Line: {context.line}")
            if hasattr(context, "function") and context.function:
                lines.append(f"Function: {context.function}")
                
        return "\n".join(lines)
        
    def _save_crash_log(self, exc_type, exc_value, exc_tb, source: str) -> Path:
        """Сохранить лог краша."""
        # Форматируем traceback
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        content = "".join(tb_lines)
        
        return self._save_crash_log_raw(
            title=f"{self.app_name} Crash Report",
            source=source,
            content=content
        )
        
    def _save_crash_log_raw(self, title: str, source: str, content: str) -> Path:
        """
        Сохранить лог краша (низкоуровневый метод).

        ПРИОРИТЕТ: Сначала сохраняем в файл, потом выводим в консоль.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        crash_file = self.crash_logs_dir / f"crash_{timestamp}.log"

        # Получаем полный лог приложения если есть callback
        app_log = ""
        if self.get_app_log_callback:
            try:
                app_log = self.get_app_log_callback()
            except Exception:
                app_log = "[Could not retrieve application log]"

        # 1. СНАЧАЛА сохраняем в файл
        saved = False
        try:
            self.crash_logs_dir.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"{title}\n")
                f.write(f"Time: {datetime.now().isoformat()}\n")
                f.write(f"Source: {source}\n")
                f.write("=" * 60 + "\n\n")
                
                # Добавляем полный лог приложения если есть
                if app_log:
                    f.write("=== APPLICATION LOG ===\n\n")
                    f.write(app_log)
                    f.write("\n\n=== CRASH INFO ===\n\n")
                
                f.write(content)
                f.flush() # Принудительно записываем на диск
            saved = True
        except Exception:
            # Если не удалось сохранить - пробуем альтернативное место
            alt_file = Path.home() / f"crash_{timestamp}.log"
            try:
                with open(alt_file, "w", encoding="utf-8") as f:
                    f.write(f"{title}\n")
                    f.write(f"Time: {datetime.now().isoformat()}\n")
                    f.write(f"Source: {source}\n")
                    f.write("=" * 60 + "\n\n")
                    
                    # Добавляем полный лог приложения если есть
                    if app_log:
                        f.write("=== APPLICATION LOG ===\n\n")
                        f.write(app_log)
                        f.write("\n\n=== CRASH INFO ===\n\n")
                    
                    f.write(content)
                    f.flush()
                crash_file = alt_file
                saved = True
            except Exception:
                pass # Ничего не можем сделать
                
        # 2. ПОТОМ выводим в консоль
        print(f"\n{'!' * 60}")
        print("CRASH DETECTED!")
        print(f"Source: {source}")
        if saved:
            print(f"Crash log saved: {crash_file}")
        else:
            print("WARNING: Could not save crash log!")
        print(f"{'!' * 60}\n")
        
        # 3. Выводим traceback в консоль для отладки
        print(content)
        
        # 4. Вызываем callback если есть
        if self.on_crash_callback:
            try:
                self.on_crash_callback(str(crash_file))
            except Exception:
                pass
                
        return crash_file
        
    def cleanup_old_logs(self, max_age_days: int = 30, max_files: int = 20) -> None:
        """
        Удалить старые логи.
        
        Args:
            max_age_days: Максимальный возраст логов в днях
            max_files: Максимальное количество файлов для сохранения
        """
        if not self.crash_logs_dir.exists():
            return
            
        try:
            # Получаем все crash_*.log файлы
            crash_files = list(self.crash_logs_dir.glob("crash_*.log"))
            
            # Сортируем по времени модификации (новые первые)
            crash_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            now = datetime.now().timestamp()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            files_to_delete = []
            
            # Отмечаем файлы старше max_age_days
            for i, f in enumerate(crash_files):
                file_age = now - f.stat().st_mtime
                
                # Удаляем если старый или если превышен лимит файлов
                if file_age > max_age_seconds or i >= max_files:
                    files_to_delete.append(f)
                    
            # Удаляем отмеченные файлы
            for f in files_to_delete:
                try:
                    f.unlink()
                except Exception:
                    pass
                    
        except Exception:
            pass  # Игнорируем ошибки при очистке


# Глобальная функция для удобства
def install_crash_handler(
    crash_logs_dir: Optional[Path] = None,
    app_name: str = "App",
    on_crash_callback: Optional[Callable[[str], None]] = None,
    get_app_log_callback: Optional[Callable[[], str]] = None,
    cleanup: bool = True,
    max_age_days: int = 30,
    max_files: int = 20,
) -> CrashHandler:
    """
    Установить глобальный обработчик крашей.

    Args:
        crash_logs_dir: Директория для сохранения логов крашей
        app_name: Имя приложения для заголовка лога
        on_crash_callback: Опциональный callback при краше
        get_app_log_callback: Callback для получения полного лога приложения
        cleanup: Выполнить очистку старых логов при установке
        max_age_days: Максимальный возраст логов в днях
        max_files: Максимальное количество файлов для сохранения

    Returns:
        Экземпляр CrashHandler
    """
    handler = CrashHandler(
        crash_logs_dir=crash_logs_dir,
        app_name=app_name,
        on_crash_callback=on_crash_callback,
        get_app_log_callback=get_app_log_callback,
    )
    
    handler.install()
    
    if cleanup:
        handler.cleanup_old_logs(max_age_days=max_age_days, max_files=max_files)
        
    return handler
