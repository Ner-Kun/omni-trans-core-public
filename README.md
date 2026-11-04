# Omni Trans Core

Ядро переводчиков Omni и общий лаунчер.

## Структура

- `omni_trans_core/` — Python-пакет ядра: окно, настройки, провайдеры, очередь переводов, локализация.
- `launcher/` — GUI-лаунчер: устанавливает, обновляет и запускает приложения.
- `tests/` — тесты ядра.
- `settings/` — локальные настройки и секреты. В git не попадают.
- `lgt_app/` — отдельный репозиторий переводчика Lorebook Gemini Translator. В этот репозиторий не входит.

## Разработка

```powershell
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe -m lgt_app.runner
```

Для тестов без окна:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe -m pytest
```

## Лицензия

GPLv3. См. `LICENSE`.
