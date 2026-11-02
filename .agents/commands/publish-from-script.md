---
description: Подготовить и после утверждения назначить выпуск YouTube, Telegram и Дзена напрямую через Codex.
---

Следуй `.agents/skills/publish-from-script/SKILL.md`, передав весь `$ARGUMENTS`.
Вход: `"<rendered_mp4>" --docx "<docx_path>"` или существующий YouTube URL.
По умолчанию — три площадки; явное ограничение пользователя приоритетнее.
Маршрут: prepare → status и preview-youtube (только новая загрузка) → общее превью → утверждение → approve с точной revision → schedule-youtube → render-texts → schedule-telegram → prepare-dzen → schedule-dzen → отдельные check-*.
Выполняй только выбранные площадки. prepare-dzen создаёт внешний черновик: до утверждения его не запускать. URL разрешает только сверку YouTube, не перезагрузку или изменение ролика. При ошибке или неопределённом результате остановись на сверке и сообщи блокер, не повторяй отправку вслепую.
Контракт и CLI: `docs/specs/content-release.md`.
