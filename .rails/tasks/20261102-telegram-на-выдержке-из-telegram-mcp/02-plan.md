# План: Telegram на выдержке из telegram-mcp

## Шаги
- [x] S1: выдержка upstream — verbatim-блоки (parse_schedule_date, allowlist, _is_flood_wait, MP4-парсер) и modified send_scheduled_file/send_scheduled_text с пометками `# upstream:`; только stdlib + telethon — файлы: telegram-publish/tg_post.py
- [x] S2: адаптер — время через parse_schedule_date, allowlist до загрузки, атрибуты видео из MP4 с fallback, FloodWait → ReleaseError без повтора; остальные гарантии без изменений — файлы: tools/publishing_telegram.py
- [x] S3: пин telethon и необязательный allowlist в примере настроек — файлы: requirements-publishing.txt, .env.example
- [x] S4: тесты AC-1…AC-5 (MP4 генерировать ffmpeg testsrc во временном каталоге) — файлы: tools/test_publishing_telegram.py, tools/test_publishing.py
- [x] S5: таблица перенесённых блоков (upstream файл:строки, verbatim|modified, sha256 блока) — файлы: telegram-publish/UPSTREAM.md

## Границы
Не трогаем: YouTube (T2) и Дзен (T4), `tools/publishing_core.py` (кроме случая, если без него нельзя — тогда `back plan`), `telegram_parts`, `reconcile_telegram`, CLI-команды, навыки и спецификацию (T5), core-монтаж, `.env`, `.local/auth/`, сессии Telegram. Никаких реальных подключений к Telegram.

## Параллелизация
Последовательно: S2 и S4 зависят от S1, исполнитель один (Pi). Claude параллельно ждёт тестовый слот и готовит T4.

## Ревью
Pi в чистом контексте ревьюит дифф против AC и сверяет verbatim-блоки с upstream через `gh api` на `0246df8c`. Claude проверяет гейты, читает дифф, прогоняет тесты под codex-test-guard. Human review: первая реальная отложка видео в канал — в отдельной приёмке с утверждением ревизии.
