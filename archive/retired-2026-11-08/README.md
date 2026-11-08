# Неиспользуемые файлы (2026-11-08)

Перенесены из активного проекта: ни навыки, ни команды, ни CLI, ни тесты на них не ссылаются. Не запускать как часть выпуска.

- `IDEA.md` — двухстрочная заметка об идее проекта; описание теперь в `README.md`.
- `docs/user-story-status.md` — исторический аудит прежней реализации (n8n, WordPress, OpenRouter).
- `tools/create_marketing_script.py` — разовый генератор DOCX для одного ролика «Бутылочное горлышко в маркетинге»; DOCX создаёт навык `video-script`.
- `tools/inspect_dzen_editor.py`, `tools/inspect_dzen_public_article.py` — разовая отладка разметки Дзена через CDP; проверку выполняет `check-dzen`.
- `tools/reorder_dzen_images.py` — разовое исправление порядка картинок одной статьи; порядок задаёт `dzen_sequence_path`.
- `dzen-publish/article_template.txt` — шаблон самостоятельного режима upstream; выпуск идёт через общий CLI.
- `Дзен статьи.docx` — рабочий список замены картинок в старых статьях Дзена (не отслеживается Git).
