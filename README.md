# SMM Agent

Codex создаёт сценарий и визуалы, монтирует запись и назначает публикации непосредственно на YouTube, в Telegram и Дзене.

1. `/video-script`: тема и время → сводка → OK → DOCX.
2. Пользователь записывает raw-видео.
3. `/render-docx-visuals "<raw_mp4>" --docx "<docx_path>"`: монтаж и проверка.
4. `/publish-from-script "<rendered_mp4>" --docx "<docx_path>"`: общее превью → OK → серверная отложка.

DOCX и MP4 имеют одинаковый base-name `YYYY-MM-DD-HHMM-Русский заголовок`. Время — Москва. Явный запрос одной площадки ограничивает выпуск ею. Существующий YouTube URL не вызывает повторную загрузку.

Готовое видео: `.tmp/rendered/YYYY-MM-DD-HHMM-Русский заголовок.mp4`. Для старых сценариев без встроенных изображений доступен резервный `render-with-visuals`; основной способ — `render-docx-visuals`.

## Настройка

```text
python -m pip install -r requirements-publishing.txt
python tools/publish_release.py auth-youtube
python tools/publish_release.py auth-telegram
```

Создайте локальный `.env` по `.env.example`. YouTube: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` от OAuth Web application и ID канала; в Google Cloud добавьте Authorized redirect URI `http://localhost:8765/` (со слешем). Authorized JavaScript origins для этого способа не нужны. Вместо пары ID/Secret можно оставить резервный OAuth Desktop JSON. Telegram: api_id/api_hash и пользовательский вход с правом публикации; `TELEGRAM_ALLOWED_CHAT_IDS` задаёт дополнительный allowlist (пустое значение отключает только этот фильтр). Дзен: авторизованный Chrome CDP. Linux — `tools/chrome_cdp.py`, Windows — `dzen-publish/ensure_cdp_chrome.ps1`; `DZEN_CDP_MODE=external` использует существующий loopback CDP без запуска локального браузера. BotFather не используется.
[Единая спецификация](docs/specs/content-release.md) содержит подробные инструкции, manifest и CLI.

Секреты — в `.env` и `.local/auth/`, вне Git. Встроенной генерации обложек API-ключ не нужен. Для монтажа нужны FFmpeg и зависимости навыка рендера.

Состояние — `.tmp/publishing/<docx-base>/`; не очищайте его до сверки результатов. CLI проверяет утверждённую версию, каналы и сроки, блокирует слепой повтор после таймаута. При наблюдаемом сбое YouTube API используется Studio с проверкой существующего ролика; record-browser только сохраняет доказательство. При ошибке инструмента или неизвестном результате — сверка и блокер, не слепой повтор.

Маршрут общего CLI: prepare → status и preview-youtube (новая загрузка) → показ комплекта → утверждение revision → approve → schedule-youtube → render-texts → schedule-telegram → Дзен во встроенном браузере Codex и record-browser → check-youtube, check-telegram. Выполняются только выбранные площадки. Существующий URL YouTube разрешает только сверку, не изменение ролика.

В Codex Дзен публикуется во встроенном браузере Codex с порядком изображений DOCX из `dzen_sequence_path`; вне Codex — адаптер общего CLI и транспорт `dzen-publish/`. Маршрут: `docs/dzen-publication-route.md`. Текущая проверка CDP подтверждает будущую очередь, но не полноценный публичный выход после срока; исчезновение из очереди не означает успех. Немедленный выпуск, перенос/отмена расписания и private-only загрузка без будущей даты общим CLI пока не поддерживаются.

Происхождение и зафиксированные версии: `youtube-publish/UPSTREAM.md`, `telegram-publish/UPSTREAM.md`, `dzen-publish/UPSTREAM.md`. Ограничения: неаудированный YouTube API-проект может оставлять ролики private; Telethon отмечен как архивный в обзоре upstream; у upstream Дзена нет лицензии, права на копирование не подтверждены. Локальные тесты не подтверждают работоспособность реальных аккаунтов. Первичная внешняя приёмка — согласованный тестовый выпуск.
После подтверждения отложки компьютер для её исполнения не нужен. Проверка фактического выхода — отдельный запуск; постоянного монитора нет.

## Разработка

Тестовые зависимости — `requirements-testing.txt`; зависимости публикации, включая Playwright и Pillow, — `requirements-publishing.txt`. Для браузерных BDD-проверок отдельно нужен Chromium Playwright. Установка зависимостей и браузера не выполняется автоматически при публикации.

Активные проверки находятся в `tools/` и `tests/bdd/`; `tools/test_skill_references.py` сверяет команды документов с argparse, пути и commit транспортов без сети. Все запуски тестов — только по политике хоста из `/root/.codex/AGENTS.md`, через предусмотренный ею guard. EVAL-набор решений агента: `.agents/skills/publish-from-script/evals/README.md`. Исторические интеграции и тесты сохранены в `archive/retired-2026-09-18/` и не входят в активный процесс.
Инструкции: `AGENTS.md`, `RECIPE.md`, `.agents/skills/`, `.agents/commands/`. Источник контракта: `docs/specs/content-release.md`.
