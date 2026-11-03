# Проверка: Каркас вендорных каталогов публикаций

## Автоматические проверки
- `codex-test-guard --timeout 20m -- .venv/bin/python -m pytest tools tests/bdd -v -p no:cacheprovider -rs` (2026-11-03, ветка `rework/publishing-solyanka` @ `ded5fce`) → **239 passed in 71.18s**, 0 failed, 0 skipped. Лог: `.tmp/pi/tests-full.log`.
- Предыдущий полный прогон (до `ded5fce`): 238 passed, 1 failed — `test_documented_repo_paths_exist` ложно принял рабочий файл `dzen.md` за корневой документ; путь в спецификации уточнён (`back implement`), `tools/test_skill_references.py` → 20 passed, затем повторный полный прогон выше.
- Регрессия core входит в прогон: 32 теста `test_read_docx`/`test_render*`/`test_visual*` прошли.

## Критерии приёмки
- AC-1: PASS — `test_youtube_vendor_matches_recorded_hash` PASSED; sha256 `yt_upload.py` = `e64e0e60…f574e` записан в `youtube-publish/UPSTREAM.md`
- AC-2: PASS — `test_vendor_dirs_have_provenance` PASSED
- AC-3: PASS — `test_yt_dry_run_ok`, `test_yt_dry_run_rejects_long_title` PASSED (subprocess `-I -S`, без сети)
- AC-4: PASS — `git check-ignore -v .youtube/token.json` → `.gitignore:9:.youtube/`
- AC-5: PASS — `git diff main --stat` по core-путям (`tools/read_docx.py`, `tools/render_video_visuals.py`, `tools/create_marketing_script.py`, core-навыки) пуст; тесты `tools/` прошли (239 passed). Действующий CLI позже меняли T2–T5 по своим планам

## Human review
Тесты только офлайн: моки YouTube API и Telethon, перехват сети Chromium. Живые аккаунты не трогались. Не доверять без человека: реальная загрузка/отложка на трёх площадках и read-only проверки (whoami, права канала, CDP) — внешние действия, ждут отдельного разрешения пользователя (issues #8/#11). Ревью кода в чистом контексте делал Pi (gpt-6-astra), отчёты в `.tmp/pi/*-review*.md`; замечания исправлены до прогона. Финальную проверку соответствия AC сделал Claude по логу прогона.
