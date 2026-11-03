# Проверка: Навыки, CLI и спецификация под солянку публикаций

## Автоматические проверки
- `codex-test-guard --timeout 20m -- .venv/bin/python -m pytest tools tests/bdd -v -p no:cacheprovider -rs` (2026-11-03, ветка `rework/publishing-solyanka` @ `ded5fce`) → **239 passed in 71.18s**, 0 failed, 0 skipped. Лог: `.tmp/pi/tests-full.log`.
- Предыдущий полный прогон (до `ded5fce`): 238 passed, 1 failed — `test_documented_repo_paths_exist` ложно принял рабочий файл `dzen.md` за корневой документ; путь в спецификации уточнён (`back implement`), `tools/test_skill_references.py` → 20 passed, затем повторный полный прогон выше.
- Регрессия core входит в прогон: 32 теста `test_read_docx`/`test_render*`/`test_visual*` прошли.

## Критерии приёмки
- AC-1: PASS — `tools/test_skill_references.py` 20 passed (действия против argparse, пути, относительные ссылки)
- AC-2: PASS — тот же тест сверяет commit таблицы транспортов с тремя UPSTREAM.md, PASSED
- AC-3: PASS — EVAL 12/12 PASS при пороге 11, critical-кейсы 7/7 PASS; `.tmp/eval/T5-eval-grading.md`
- AC-4: PASS — E05, E07, E09 PASS: агент останавливается на сверке и не повторяет внешнее действие
- AC-5: PASS — `git diff main --stat -- .agents/skills/{video-script,ru-text,slop-stop-main,render-docx-visuals,render-with-visuals}` пуст

## Human review
Тесты только офлайн: моки YouTube API и Telethon, перехват сети Chromium. Живые аккаунты не трогались. Не доверять без человека: реальная загрузка/отложка на трёх площадках и read-only проверки (whoami, права канала, CDP) — внешние действия, ждут отдельного разрешения пользователя (issues #8/#11). Ревью кода в чистом контексте делал Pi (gpt-6-astra), отчёты в `.tmp/pi/*-review*.md`; замечания исправлены до прогона. Финальную проверку соответствия AC сделал Claude по логу прогона.

## EVALs
- Набор: `.agents/skills/publish-from-script/evals/evals.json` (12 кейсов, 7 critical) — метрика: PASS по assertions рубрики — порог: ≥11/12 и 0 FAIL в critical — результат: **12/12 PASS, 0 critical FAIL** (E06 частично: повторная проверка запаса после загрузки не упомянута).
- Прогон: Pi (gpt-6-astra) в чистом контексте, без доступа к evals/ и .rails/; ответы `.tmp/eval/answers.md`, оценка Claude `.tmp/eval/T5-eval-grading.md`.
- Ограничение: проверяет ясность инструкций на модели Pi, не на Codex/Claude.
