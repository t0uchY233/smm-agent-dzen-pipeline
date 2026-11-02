# План: YouTube на вендорном yt_upload.py с отложкой

## Шаги
- [ ] S1: адаптер — загрузка вендорного модуля через importlib, `release_plan`, `validate_plan`, insert телом из upstream `build_body` с ретраем 5xx в той же resumable-сессии; прежние гарантии (канал, marker, upload_attempted, youtube_id read-only, двухшаговая отложка) сохранить — файлы: tools/publishing_youtube.py
- [ ] S2: upstream-валидация на prepare — файлы: tools/publishing_core.py
- [ ] S3: действие `preview-youtube --release` (upstream preview, без сети) — файлы: tools/publish_release.py
- [ ] S4: тесты AC-1…AC-4; существующие тесты не ослаблять, правка фикстур только при необходимости (например, валидный размер обложки) — файлы: tools/test_publishing_youtube.py, tools/test_publishing.py
- [ ] S5: раздел «Как используется» в описании вендора — файлы: youtube-publish/UPSTREAM.md

## Границы
Не трогаем: `youtube-publish/yt_upload.py`, `SETUP.md`, `LICENSE` (побайтно upstream); OAuth-поток `youtube_service` и `auth-youtube`; Telegram и Дзен; core-монтаж; навыки и спецификацию (это T5); `.env`, `.local/auth/`. Никаких реальных вызовов YouTube API.

## Параллелизация
Последовательно: S2–S4 зависят от функций S1, а исполнитель один (Pi). Пока Pi работает, Claude готовит дизайн T3.

## Ревью
Pi в чистом контексте (`/new`) ревьюит дифф T2 против AC и правила «вендор неизменен». Claude проверяет гейты, читает дифф и прогоняет тесты под codex-test-guard. Зона human review: поведение при неаудированном проекте и реальная отложка — отдельная приёмка (issue #8) с утверждением ревизии.
