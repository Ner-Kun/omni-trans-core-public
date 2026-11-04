# Omni Trans Core

Ядро переводчиков Omni и общий GUI-лаунчер.

## Структура

- `omni_trans_core/` — Python-пакет ядра: Fluent-окно, настройки, провайдеры через litellm, очередь переводов, кэш, локализация, профили промптов.
- `launcher/` — GUI-лаунчер: устанавливает, обновляет и запускает приложения.
- `tests/` — тесты ядра.
- `settings/` — локальные настройки и секреты. В git не попадают.
- `lgt_app/` — отдельный репозиторий переводчика Lorebook Gemini Translator. В этот репозиторий не входит.

## Возможности

- Один транспорт — litellm: OpenAI, Mistral, OpenRouter, DeepSeek, Ollama, LM Studio, NVIDIA NIM, Google Gemini.
- Несколько API-ключей на соединение: ротация, RPM и cooldown по каждому ключу.
- Профили промптов живут в `settings/<app_id>/prompts/`; дефолт задаёт приложение.
- Тёмный интерфейс на QFluentWidgets: навигация, карточки, Fluent-диалоги, `InfoBar` вместо тостов.
- Кэш переводов рядом с файлом проекта.

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

## Публичная сборка

Публичная версия — отдельный репозиторий-снимок. Сборка:

```powershell
.venv\Scripts\python.exe tools\export_public.py
```

Скрипт берёт `git archive HEAD`, выбрасывает внутренние файлы по `.gitattributes` и коммитит снимок.

## Лицензия

GPLv3. См. `LICENSE`.
