# Дизайн: Каркас вендорных каталогов публикаций

## Задача
Подготовить основу «солянки»: вендорные каталоги YouTube и Telegram рядом с уже существующим `dzen-publish/`. У каждого — зафиксированный upstream commit, лицензия и `UPSTREAM.md`. Поведение действующего CLI публикаций в этой задаче не меняется: адаптеры подключаем в T2/T3.

## Решение
- `youtube-publish/`: дословная копия `tools/yt_upload.py` и `tools/yt_upload_SETUP.md` (→ `SETUP.md`) из hassancs91/claude-youtube-editor @ `a6ac742b44520fd3c6aeaf3cd754e113fa334fed`, `LICENSE` (MIT) и `UPSTREAM.md` с commit, sha256 файлов и списком будущих расширений (publishAt МСК, канал, дубли, ревизия).
- `telegram-publish/`: пока только `LICENSE` (Apache-2.0) и `UPSTREAM.md` (chigwell/telegram-mcp @ `0246df8c3c99818d68f50e8591b2d3dda8363f81`, какие функции берём и почему без MCP-сервера). Сам код-выдержка — в T3: это инженерная работа, а не копирование.
- `dzen-publish/UPSTREAM.md`: перенос из wip-ветки + пометка, что у upstream нет лицензии.
- `.gitignore`: `.youtube/`. Upstream кладёт туда OAuth-токен, в git он попасть не должен.
- Тест `tools/test_vendor_layout.py`: у каждого вендора есть LICENSE и UPSTREAM.md с 40-символьным commit; sha256 вендорных файлов совпадает с записанным; `yt_upload.py upload --dry-run` валидирует план без Google-библиотек и сети.
- Отдельным шагом коммитим инфраструктуру rails (`.agents/skills/engineering-rails/`, симлинк `.claude/skills/`, `skills-lock.json`, `.rails/`): это общее состояние для Claude и Pi.
- Риск: у Andrrreyiv/dzen-publish нет лицензии, формально прав на копию нет. Варианты: спросить автора или оставить на свой риск. Рекомендую спросить автора, а до ответа оставить как есть.

## Критерии приёмки
- AC-1: `youtube-publish/yt_upload.py` и `SETUP.md` побайтно совпадают с upstream на `a6ac742b`, sha256 записаны в `UPSTREAM.md` — проверка: тест `test_youtube_vendor_matches_recorded_hash` + ручная сверка `gh api` с локальным sha256
- AC-2: у `youtube-publish/`, `telegram-publish/`, `dzen-publish/` есть `UPSTREAM.md` с полным commit, у первых двух есть `LICENSE` — проверка: тест `test_vendor_dirs_have_provenance`
- AC-3: `python youtube-publish/yt_upload.py upload plan.json --dry-run` на тестовом плане печатает превью и `dry-run OK`, а план с заголовком в 101 символ отклоняется — проверка: тесты `test_yt_dry_run_ok` / `test_yt_dry_run_rejects_long_title` (subprocess, без сети)
- AC-4: `.youtube/` игнорируется git — проверка: `git check-ignore .youtube/token.json`
- AC-5: core и действующий CLI не изменены — проверка: `git diff main --stat` не содержит `tools/publish*`, `tools/render*`, `tools/read_docx.py`, `.agents/skills/{video-script,ru-text,slop-stop-main,render-*}`; существующие тесты `tools/` проходят под `codex-test-guard`
