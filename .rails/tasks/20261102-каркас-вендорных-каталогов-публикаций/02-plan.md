# План: Каркас вендорных каталогов публикаций

## Шаги
- [x] S1: закоммитить инфраструктуру rails (навык, симлинк, lock, состояние) — файлы: .agents/skills/engineering-rails/**, .claude/skills/engineering-rails, skills-lock.json, .rails/**
- [x] S2: вендор YouTube — дословные yt_upload.py и SETUP.md, LICENSE, UPSTREAM.md с sha256; .youtube/ в .gitignore — файлы: youtube-publish/yt_upload.py, youtube-publish/SETUP.md, youtube-publish/LICENSE, youtube-publish/UPSTREAM.md, .gitignore
- [x] S3: вендор Telegram — LICENSE и UPSTREAM.md (что берём из telegram-mcp и почему) — файлы: telegram-publish/LICENSE, telegram-publish/UPSTREAM.md
- [x] S4: dzen-publish/UPSTREAM.md из wip + пометка о лицензии — файлы: dzen-publish/UPSTREAM.md
- [x] S5: тест вендорной раскладки и dry-run YouTube — файлы: tools/test_vendor_layout.py
  - Тест создан. Оба запуска (этот файл и весь `tools/`) через `codex-test-guard --timeout 10m` заблокированы до старта pytest: exit 75, `memory.high utilization 99.2%`, swap `100.0%`, недостаточно MemAvailable. Приёмка тестами не подтверждена; нужен повтор после освобождения памяти.
  - `git check-ignore .youtube/token.json` → `.youtube/token.json`. SHA-256 трёх файлов YouTube повторно сверен с upstream через `gh api`; совпадает. `git diff --check` без замечаний.

Исполнитель S2–S5 — Pi (терминал Orca), ревью — Pi в чистом контексте, приёмка гейтов — Claude. S1 делает Claude.
