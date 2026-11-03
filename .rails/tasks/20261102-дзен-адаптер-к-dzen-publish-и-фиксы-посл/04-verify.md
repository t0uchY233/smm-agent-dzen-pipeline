# Проверка: Дзен: адаптер к dzen-publish и фиксы после реальной публикации

## Автоматические проверки
- `codex-test-guard --timeout 20m -- .venv/bin/python -m pytest tools tests/bdd -v -p no:cacheprovider -rs` (2026-11-03, ветка `rework/publishing-solyanka` @ `ded5fce`) → **239 passed in 71.18s**, 0 failed, 0 skipped. Лог: `.tmp/pi/tests-full.log`.
- Предыдущий полный прогон (до `ded5fce`): 238 passed, 1 failed — `test_documented_repo_paths_exist` ложно принял рабочий файл `dzen.md` за корневой документ; путь в спецификации уточнён (`back implement`), `tools/test_skill_references.py` → 20 passed, затем повторный полный прогон выше.
- Регрессия core входит в прогон: 32 теста `test_read_docx`/`test_render*`/`test_visual*` прошли.

## Критерии приёмки
- AC-1: PASS — `test_all_dzen_actions_require_approval_before_cdp[prepare|schedule|check-dzen]`, `test_dzen_revision_binds_all_materials[article|sequence|image|footer]`, `test_dzen_cli_dispatch_and_exit_code` (12) PASSED
- AC-2: PASS — `test_docx_sequence_identity_is_checked_after_reapproval[swapped|replaced|moved|source-text]`, `test_docx_image_count_is_required_before_browser[missing-sequence|missing-image|extra-image]`, `test_extractor_preserves_docx_image_bytes_and_context` PASSED
- AC-3: PASS — `test_dzen_localized_schedule_date_is_verified_exactly` и сценарии наблюдения PASSED
- AC-4: PASS — `tools/test_chrome_cdp.py` 14 passed
- AC-5: PASS — `tests/bdd/test_dzen_observation.py` 41 passed в изолированном Chromium
- AC-6: PASS — core-пути в `git diff main --stat` пусты, `render_qa` отсутствует (`git ls-files | grep render_qa` → 0), полный прогон `tools tests/bdd` 239 passed; совместимость revision без Дзена — `test_non_dzen_revision_matches_legacy_formula` (9) PASSED

## Human review
Тесты только офлайн: моки YouTube API и Telethon, перехват сети Chromium. Живые аккаунты не трогались. Не доверять без человека: реальная загрузка/отложка на трёх площадках и read-only проверки (whoami, права канала, CDP) — внешние действия, ждут отдельного разрешения пользователя (issues #8/#11). Ревью кода в чистом контексте делал Pi (gpt-6-astra), отчёты в `.tmp/pi/*-review*.md`; замечания исправлены до прогона. Финальную проверку соответствия AC сделал Claude по логу прогона.
