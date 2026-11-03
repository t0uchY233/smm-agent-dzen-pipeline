# Проверка: Telegram на выдержке из telegram-mcp

## Автоматические проверки
- `codex-test-guard --timeout 20m -- .venv/bin/python -m pytest tools tests/bdd -v -p no:cacheprovider -rs` (2026-11-03, ветка `rework/publishing-solyanka` @ `ded5fce`) → **239 passed in 71.18s**, 0 failed, 0 skipped. Лог: `.tmp/pi/tests-full.log`.
- Предыдущий полный прогон (до `ded5fce`): 238 passed, 1 failed — `test_documented_repo_paths_exist` ложно принял рабочий файл `dzen.md` за корневой документ; путь в спецификации уточнён (`back implement`), `tools/test_skill_references.py` → 20 passed, затем повторный полный прогон выше.
- Регрессия core входит в прогон: 32 теста `test_read_docx`/`test_render*`/`test_visual*` прошли.

## Критерии приёмки
- AC-1: PASS — `test_tg_post_verbatim_blocks_match_upstream` PASSED; ручная сверка блоков — ревью Pi T3
- AC-2: PASS — `test_telegram_server_schedule_and_repeat`, `test_telegram_schedule_parsed_via_upstream_msk` PASSED
- AC-3: PASS — `test_telegram_video_attributes_from_mp4` PASSED
- AC-4: PASS — `test_telegram_allowlist_blocks_before_upload` PASSED
- AC-5: PASS — `test_telegram_flood_wait_is_not_retried` (2 варианта) PASSED
- AC-6: PASS — `tools/test_publishing.py` 38 passed под codex-test-guard

## Human review
Тесты только офлайн: моки YouTube API и Telethon, перехват сети Chromium. Живые аккаунты не трогались. Не доверять без человека: реальная загрузка/отложка на трёх площадках и read-only проверки (whoami, права канала, CDP) — внешние действия, ждут отдельного разрешения пользователя (issues #8/#11). Ревью кода в чистом контексте делал Pi (gpt-6-astra), отчёты в `.tmp/pi/*-review*.md`; замечания исправлены до прогона. Финальную проверку соответствия AC сделал Claude по логу прогона.
