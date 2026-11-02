# План: Навыки, CLI и спецификация под солянку публикаций

## Шаги
- [x] S1: EVAL-набор до правки навыков — 12 кейсов (промпт, ожидаемое поведение, assertions, категория critical/normal), рубрика и инструкция прогона — файлы: .agents/skills/publish-from-script/evals/evals.json, .agents/skills/publish-from-script/evals/README.md
- [x] S2: навык публикации и его команда под новый маршрут CLI — файлы: .agents/skills/publish-from-script/SKILL.md, .agents/commands/publish-from-script.md
- [x] S3: навык Дзена и восстановление CDP под CLI и Linux/Windows/external — файлы: .agents/skills/dzen/SKILL.md, .agents/skills/dzen/references/cdp-recovery.md
- [x] S4: дирижёр процесса — файлы: .agents/skills/smm-conductor/SKILL.md
- [x] S5: спецификация, маршрут Дзена, AGENTS/README, зависимости — файлы: docs/specs/content-release.md, docs/dzen-publication-route.md, AGENTS.md, README.md, requirements-publishing.txt, requirements-testing.txt, dzen-publish/README.md
- [x] S6: тест ссылок навыков на CLI, файлы и commit вендоров — файлы: tools/test_skill_references.py

## Границы
Не трогаем: код адаптеров и CLI (T2–T4), core-навыки и их команды, `tone-of-voice.md`, `archive/`, `.env`, `.local/auth/`. Не добавляем новых команд CLI: если навыку не хватает команды, это фиксируется как находка, а не дописывается.

## Параллелизация
Последовательно: S1 до S2–S4, чтобы EVAL не подгонялся под текст навыков; исполнитель один (Pi). EVAL-прогон (verify) выполняет Pi в отдельной чистой сессии, оценивает Claude.

## Ревью
Pi в чистом контексте ревьюит навыки/спецификацию против кода CLI (`tools/publish_release.py --help`, адаптеры) и правил AGENTS.md. Claude — гейты, тест ссылок под codex-test-guard, оценка EVAL по assertions. Human review: тексты навыков читает пользователь при первом реальном выпуске.
