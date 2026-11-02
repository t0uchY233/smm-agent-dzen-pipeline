# План: Каркас вендорных каталогов публикаций

## Шаги
- [x] S1: закоммитить инфраструктуру rails (навык, симлинк, lock, состояние) — файлы: .agents/skills/engineering-rails/**, .claude/skills/engineering-rails, skills-lock.json, .rails/**
- [ ] S2: вендор YouTube — дословные yt_upload.py и SETUP.md, LICENSE, UPSTREAM.md с sha256; .youtube/ в .gitignore — файлы: youtube-publish/yt_upload.py, youtube-publish/SETUP.md, youtube-publish/LICENSE, youtube-publish/UPSTREAM.md, .gitignore
- [ ] S3: вендор Telegram — LICENSE и UPSTREAM.md (что берём из telegram-mcp и почему) — файлы: telegram-publish/LICENSE, telegram-publish/UPSTREAM.md
- [ ] S4: dzen-publish/UPSTREAM.md из wip + пометка о лицензии — файлы: dzen-publish/UPSTREAM.md
- [ ] S5: тест вендорной раскладки и dry-run YouTube — файлы: tools/test_vendor_layout.py

Исполнитель S2–S5 — Pi (терминал Orca), ревью — Pi в чистом контексте, приёмка гейтов — Claude. S1 делает Claude.
