# Дизайн: Telegram на выдержке из telegram-mcp

## Задача бизнеса
Видео с текстом должно встать в серверную отложку Telegram-канала на согласованное время по Москве, без дублей и без бота. Текущий модуль работает, но весь написан с нуля и отправляет видео с захардкоженными 1920×1080 и без проверки разрешённого чата на уровне транспорта. Берём проверенные куски chigwell/telegram-mcp (1955★, Apache-2.0): разбор времени отложки, чтение реальных параметров MP4, allowlist чатов, распознавание flood-wait. Наши гарантии сохраняем.

## Ограничения
- Внешние действия только после утверждения ревизии. Запас ≥ 1 мин проверяется после загрузки файла, перед каждой частью.
- Пользовательская MTProto-сессия (Telethon, `.local/auth/telegram.session`), без бота. `flood_sleep_threshold=0`: молча не спим и не повторяем.
- Свободного инструмента отправки нет: MCP-сервер и runtime upstream не переносим.
- Без сети в тестах.

## Компоненты и интеграция
- `telegram-publish/tg_post.py` — выдержка из upstream @ `0246df8c`. Каждый блок помечен комментарием `# upstream: файл:строки (verbatim или modified: что изменено)`:
  - verbatim: `parse_schedule_date` (runtime.py), `_parse_allowed_chat_ids`, `is_chat_allowed`, `check_chat_access` (runtime.py; `get_marked_id` берём из `telethon.utils`), `_is_flood_wait` (runtime.py), `_video_send_attributes`, `_mp4_video_attributes`, `_find_box`, `_parse_moov`, `_parse_mvhd`, `_parse_trak`, `_parse_tkhd` (tools/media.py);
  - modified: `send_scheduled_file(client, entity, path, caption, dt)` по мотивам `send_file`. Возвращает объект сообщения (upstream отбрасывает ID, а нам он нужен для сверки), `parse_mode=None`, без album/topic/custom emoji/путей из MCP-контекста; `send_scheduled_text(...)` по мотивам `send_scheduled_message`.
  - Модуль импортирует только stdlib и telethon, без `mcp`, pypdf и прочего.
- `tools/publishing_telegram.py` — адаптер:
  - время: `parse_schedule_date(expected.isoformat())` вместо голого `expected`. Ошибка «в прошлом» → `ReleaseError`;
  - allowlist: если задан `TELEGRAM_ALLOWED_CHAT_IDS`, канал выпуска обязан в него входить (`check_chat_access`), иначе `ReleaseError` до загрузки;
  - видео: атрибуты из `_video_send_attributes(path)` вместо захардкоженных 1920×1080 + duration из ffprobe. Если парсер вернул None, fallback на текущие значения;
  - `FloodWaitError` → `ReleaseError('Telegram просит подождать N с …')`, часть остаётся `sending` → сверка, без повтора;
  - без изменений: `verify_channel`, `check_telegram`, `reconcile_telegram`, разбиение текста `telegram_parts`, защита от слепого повтора, лимит размера по Premium.
- `requirements-publishing.txt`: пин `telethon>=1.45,<2`.
- `.env.example`: необязательный `TELEGRAM_ALLOWED_CHAT_IDS=` с комментарием.
- `telegram-publish/UPSTREAM.md`: таблица фактически перенесённых блоков (verbatim/modified) и sha256 `tg_post.py`.

## Альтернативы
- A. Выдержка в `tg_post.py` + тонкий адаптер (выбрано). Плюсы: только нужный код, видно, что взято, нет MCP-рантайма. Минусы: обновления upstream переносим вручную, по таблице.
- B. Поставить `telegram-mcp` пакетом и импортировать `telegram_mcp.tools.media`. Плюсы: обновление через pip. Минусы: при импорте поднимается весь runtime (MCP, клиент из env, pypdf, qrcode), функции обёрнуты в `@mcp.tool` и возвращают строки без ID сообщения. Для сверки дублей это непригодно.
- C. Запустить MCP-сервер с `TELEGRAM_EXPOSED_TOOLS=read-only+send_file`. Отклонено пользователем: агент получил бы отправку в обход гейта ревизии.

## Решение и обоснование
Вариант A. Повторяет паттерн Дзена и YouTube (T2): транспорт заимствован, гейты наши. Выигрыш по существу: правильные размеры и длительность видео в клиентах, allowlist как второй рубеж против отправки не в тот канал, понятная ошибка flood-wait вместо «неизвестной».

## Допущения и риски
- Telethon архивирован (GitHub подтверждает archived). Пин `<2` защищает от неожиданной мажорной версии. Миграция на kurigram — отдельная задача, если Telethon перестанет работать с текущим слоем MTProto.
- Upstream считает время без часового пояса UTC. Адаптер всегда передаёт aware-время, переведённое из Europe/Moscow, так что расхождения нет. Это проверяет тест.
- MP4-парсер upstream не проверен на наших рендерах. Тест на реальном коротком MP4 из FFmpeg (1920×1080) обязателен. При None — fallback.
- Allowlist необязателен (пустой = выключен), как в upstream. Главная проверка остаётся прежней: `TELEGRAM_CHANNEL_ID` == канал утверждённого выпуска.

## Критерии приёмки
- AC-1: `tg_post.py` содержит перечисленные блоки с пометками `# upstream:`, verbatim-блоки текстуально совпадают с upstream на `0246df8c` — проверка: тест `test_tg_post_verbatim_blocks_match_upstream` (сравнение с зафиксированными sha256 блоков в UPSTREAM.md) + ручная сверка ревьюером
- AC-2: отложка ставится на то же UTC-время, что `scheduled_at` по МСК; прошедшее время → ReleaseError без отправки — проверка: тесты `test_telegram_server_schedule_and_repeat` (существующий) и `test_telegram_schedule_parsed_via_upstream_msk`
- AC-3: видео уходит с реальными шириной, высотой и длительностью из файла — проверка: тест `test_telegram_video_attributes_from_mp4` (MP4 из ffmpeg `testsrc`, 1920×1080, 2 с)
- AC-4: при `TELEGRAM_ALLOWED_CHAT_IDS` без канала выпуска ничего не загружается и не отправляется — проверка: тест `test_telegram_allowlist_blocks_before_upload`
- AC-5: FloodWaitError на отправке → ReleaseError с секундами, часть в `sending`, повторный запуск блокируется до сверки — проверка: тест `test_telegram_flood_wait_is_not_retried`
- AC-6: прежние тесты Telegram в `tools/test_publishing.py` проходят без ослабления assert'ов — проверка: прогон под codex-test-guard
