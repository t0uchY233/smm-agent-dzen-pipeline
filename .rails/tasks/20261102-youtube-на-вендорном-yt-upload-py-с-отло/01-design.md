# Дизайн: YouTube на вендорном yt_upload.py с серверной отложкой

## Задача бизнеса
Ролик Сергея Веселкова должен уйти на YouTube приватно и с отложкой на согласованное время по Москве, без дублей и без ручной работы в Studio. Сейчас для этого используется самописный модуль. Переводим его на проверенный upstream (hassancs91/claude-youtube-editor, 362★): валидация плана и лимиты, превью, resumable-загрузка с ретраями. Наши гарантии сохраняются.

## Ограничения
- Внешние действия только после утверждения ревизии (`Release.require_approval`); запас ≥ 1 мин проверяется перед insert и перед update.
- Вендорный `youtube-publish/yt_upload.py` остаётся побайтно равным upstream (тест T1). Расширения живут в адаптере `tools/publishing_youtube.py`.
- OAuth проекта сохраняется: Web client (`YOUTUBE_CLIENT_ID/SECRET`, callback `http://localhost:8765/`) или резервный Desktop JSON, токен `.local/auth/youtube-token.json`. Upstream `get_creds()` и `.youtube/` не используются.
- Без сети в тестах; реальная загрузка — только в отдельной приёмке с утверждением (issue #8).

## Компоненты и интеграция
- `tools/publishing_youtube.py`: загрузка модуля `youtube-publish/yt_upload.py` через importlib (в имени каталога дефис). Функции:
  - `release_plan(release)` → upstream-план: `video`/`thumbnail` абсолютными путями, `title`, `description`, `tags=[marker]`, `privacy='private'`, `madeForKids`, `categoryId` только если задан `manifest.youtube_category`.
  - `validate_plan(plan)` → upstream `validate()`; ошибки → `ReleaseError`.
  - `schedule_youtube`: insert телом из upstream `build_body()` без `publishAt` → `thumbnails.set` → `videos.update(publishAt)` → read-back. Цикл `next_chunk` как в upstream `do_upload`: ретрай 5xx до 5 раз с backoff внутри той же resumable-сессии, это не создаёт второй ролик.
  - Без изменений: `youtube_service`, `verify_channel`, `check_youtube`, защита `upload_attempted`/marker, read-only режим при `youtube_id`.
- `tools/publishing_core.py`: `validate_manifest` для YouTube без `youtube_id` вызывает `publishing_youtube.validate_plan(release_plan(manifest))` (ленивый импорт, без сети).
- `tools/publish_release.py`: новое действие `preview-youtube --release` — upstream `preview()` по плану выпуска без сети, для показа в комплекте утверждения. `auth-youtube` не меняется.
- `youtube-publish/UPSTREAM.md`: раздел «Как используется» со списком импортируемых символов.

## Альтернативы
- A. Адаптер импортирует upstream-функции, вендорный файл не трогаем. Плюсы: обновление upstream = замена файла + тесты, дифф виден сразу. Минусы: цикл загрузки и OAuth остаются у нас, upstream `do_upload` не используется целиком.
- B. Править вендорную копию: добавить в `do_upload` publishAt, канал, marker, наш OAuth. Плюсы: один файл. Минусы: расходимся с upstream, обновлять больно, бизнес-гейты попадают в чужой код.
- C. Вызывать `yt_upload.py upload` подпроцессом. Плюсы: максимум переиспользования. Минусы: ID ролика только из stdout, нет state/marker до insert, свой токен в `.youtube/`, отложку всё равно делать отдельно.

## Решение и обоснование
Вариант A. Он соответствует правилу «вендорный код меняем минимально» и паттерну Дзена: транспорт снаружи, гейты у нас. Двухшаговая схема (insert private → обложка → publishAt) сохраняется: если обложка не встала, ролик не уходит в отложку без неё. Схема проверена на канале 22.09.

## Допущения и риски
- Категория: upstream по умолчанию ставит 28 (Science & Technology), текущий модуль её не задаёт (берётся умолчание канала). Сохраняем текущее поведение, категорию задаём только явным `manifest.youtube_category`, чтобы не выдумывать правило.
- Новые ограничения upstream: обложка ≤ 2 МБ, заголовок без угловых скобок и вертикальной черты, теги ≤ 460 символов. Раньше такой комплект проходил prepare и падал в API, теперь отклоняется до утверждения. Это изменение поведения в безопасную сторону.
- Неаудированный Google-проект может держать ролики private и после `publishAt`. Read-back проверяет `publishAt`, но не фактический выход: его подтверждает `check-youtube` после срока. 22.09 отложка на канале сработала.
- Импорт upstream-модуля делает `sys.stdout.reconfigure(utf-8)`: безопасно, CLI и так печатает UTF-8.

## Критерии приёмки
- AC-1: `schedule_youtube` строит тело insert через upstream `build_body` (private, без publishAt, теги = [marker]) и назначает publishAt по МСК отдельным update, только после обложки — проверка: тест `test_youtube_private_upload_then_schedule_and_no_duplicate` (обновлённый) + `test_youtube_insert_body_from_upstream`
- AC-2: ошибки upstream `validate` (заголовок с `|`, обложка > 2 МБ) дают `ReleaseError` на `prepare` и не вызывают API — проверка: тесты `test_youtube_upstream_validation_blocks_prepare[title_pipe|thumb_size]`
- AC-3: ответ 503 на `next_chunk` повторяется в той же сессии, insert вызывается ровно один раз; после 5 неудач — ошибка без повторного insert — проверка: тест `test_youtube_resumable_retries_5xx_without_second_insert`
- AC-4: `preview-youtube --release` печатает upstream-превью без сети и OAuth — проверка: тест `test_preview_youtube_cli_offline`
- AC-5: прежние гарантии не ослаблены: неизвестный результат загрузки блокирует повтор, `youtube_id` = только чтение, чужой канал и несовпадение времени не считаются успехом — проверка: существующие тесты `tools/test_publishing.py` проходят без ослабления assert'ов
- AC-6: вендорный файл не изменён — проверка: `test_youtube_vendor_matches_recorded_hash` из T1
