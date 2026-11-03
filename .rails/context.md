# Контекст проекта

Актуально на: 2026-11-02

## Архитектура
Локальный агентный пайплайн выпуска видео Сергея Веселкова (Python 3, FFmpeg, Playwright). Сервера нет: всё запускает агент (Codex/Claude/Pi) из CLI и навыков `.agents/skills/`.
- **Core (не трогаем в этой переработке):** `tone-of-voice.md` → навык `video-script` (+ `ru-text`, `slop-stop-main`) → DOCX в `.tmp/teleprompter/` (`tools/create_marketing_script.py`, `tools/read_docx.py`) → запись raw-видео пользователем → монтаж `render-docx-visuals` / `render-with-visuals` (`tools/render_video_visuals.py`, Whisper large-v3, FFmpeg) → MP4 в `.tmp/rendered/`.
- **Публикационный слой (пересобираем):** `tools/publish_release.py` (CLI) → `tools/publishing_core.py` (manifest, revision, approval, state, lock) → адаптеры `tools/publishing_youtube.py` (Google API, OAuth), `tools/publishing_telegram.py` (Telethon, пользовательская сессия), Дзен через `dzen-publish/publish_dzen.py` (Playwright/CDP, вендор Andrrreyiv/dzen-publish). Навыки: `publish-from-script`, `dzen`, `smm-conductor`.
- Состояние выпусков: `.tmp/publishing/{docx-base}/` (manifest.json, state.json, events.jsonl), журнал `publish-log.md`.
- Тесты: `tools/test_*.py` (pytest, `pytest.ini`: testpaths=tools).

## Предметная область
- **Выпуск (release)** — один ролик и тексты к нему для YouTube, Telegram и Дзена с общей датой публикации по Москве.
- **Ревизия (revision)** — хеш утверждённого комплекта материалов. Утверждение пользователя относится к конкретной ревизии.
- **Отложка** — серверное расписание площадки: YouTube `publishAt`, Telegram scheduled messages, отложенная публикация в редакторе Дзена.
- **Base-name** `YYYY-MM-DD-HHMM-Русский заголовок` — общий для DOCX и MP4, время = план публикации МСК.
- Статусы площадок: `prepared`, `uploaded`, `scheduled`, `published`, `failed`; промежуточные `uploading`/`sending`/`unconfirmed` требуют сверки.

## Бизнес-правила
- Никаких внешних действий (загрузка, отложка, публикация, правка опубликованного) без явного утверждения конкретной ревизии пользователем. Подстановка полученного YouTube URL вместо `{youtube_url}` входит в утверждение.
- До отправки запас до времени публикации ≥ 1 минуты; прошедшее время в API не подставлять.
- Без авторизации или при неопределённом результате: не повторять загрузку/отправку вслепую, сначала сверить существующий объект (защита от дублей).
- Видимость по умолчанию: YouTube — private до `publishAt`; немедленная открытая публикация только по прямому поручению.
- Дзен: сверка текста, порядка всех изображений и пяти активных ссылок финального блока до отправки.
- Частичный сбой одной площадки не стирает успехи других. План и подтверждённый результат хранятся раздельно.
- Тексты проходят tone-of-voice → ru-text → slop-stop (≥ 35/50); цифры и кейсы не выдумываются.

## Продакшн
Продакшен-сервера нет. «Прод» — реальные аккаунты: YouTube-канал `UCPL3MascatiZkkBwruDgPYA`, Telegram-канал (ID в `.env`), Дзен-канал «Экономика не для всех!» (`dzen.ru/profile/editor/ekonomikadliavseh`). Последние подтверждённые отложки: YouTube и Дзен 22–24.09, Дзен 01.10 (`publish-log.md`). Мониторинга нет: фактический выход проверяется отдельным запуском `check-*`. CI на GitHub не настроен.

## Решения (ADR)
- 2026-09-18: n8n, Drive, Sheets, WordPress и блог veselkov исключены (архив `archive/retired-2026-09-18/`).
- Дзен: вендорная копия Andrrreyiv/dzen-publish (commit `a6bbc78b…`) с локальными расширениями; другой механизм редактора не создаётся. Browser/Computer Use — только после наблюдаемого сбоя основного маршрута.
- 2026-11-02 (переработка): публикационный слой — «солянка» из вендорных upstream-кусков с `UPSTREAM.md` у каждого. YouTube = hassancs91/claude-youtube-editor `tools/yt_upload.py` @ `a6ac742b` (MIT) + наша серверная отложка `publishAt`. Telegram = выдержка постинга из chigwell/telegram-mcp @ `0246df8c` (Apache-2.0) как код, не как MCP-сервер. База — чистый `main` (`c60d24a`); `wip/bdd-tests-dzen-route` и PR #12/#13 — только справочник.
- Telegram — пользовательская MTProto-сессия, не бот (серверная отложка недоступна ботам).
- Исполнитель и ревьюер кода — Pi (терминал Orca), оркестратор и гейты — Claude; сабагенты Claude не используются.

## Доступы агента
- Можно: читать и менять код репозитория в рамках плана текущей задачи (`rails.py can-edit`), создавать файлы в `.tmp/` и скретч-каталоге, читать публичные upstream-репозитории через `gh`.
- Запрещено: читать или выводить `.env`, `.local/auth/` (токены, сессии, cookies); просить коды и пароли в чате; запускать реальные загрузки и публикации без утверждения ревизии; push, merge, закрытие PR и issues без явного разрешения; трогать `archive/` и core-навыки; очищать `.tmp/publishing/` и `publish-log.md`.
- Тесты: только через `/root/.local/bin/codex-test-guard`, один тестовый процесс на хост; обычные тесты не читают рабочий `.env` и не публикуют.
- Полный прогон `tools tests/bdd` занимает ~72 с и ~1,5 ГиБ (239 тестов на 2026-11-03). При нехватке памяти `host-job-run` отказывает с кодом 75: ставить прогон в фоновый цикл с повтором, запускать сразу после implement каждой задачи, не копить проверку до конца.
