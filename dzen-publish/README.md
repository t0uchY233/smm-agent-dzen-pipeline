# dzen-publish в SMM Agent

Основа — [Andrrreyiv/dzen-publish](https://github.com/Andrrreyiv/dzen-publish): Playwright подключается к авторизованному Chrome через CDP и использует штатный редактор. См. [зафиксированную версию и расширения](UPSTREAM.md).

## Подключение

Зависимости транспорта, включая `playwright` и `Pillow`: `python -m pip install -r requirements-publishing.txt`.

Windows: `start_chrome.bat` или `ensure_cdp_chrome.ps1`. Linux: `python tools/chrome_cdp.py` в рабочем столе либо с постоянным Xvfb DISPLAY. Войти в Дзен вручную в отдельном профиле. `CHROME_BINARY`, `DZEN_CDP_URL` и `DZEN_CHROME_PROFILE` настраивают окружение; канал выпуска берётся из manifest. `DZEN_CDP_MODE=external` запрещает локальный запуск Chrome и использует уже доступный loopback CDP, например через SSH-туннель. Запуск локального Chrome от root запрещён.

```text
python dzen-publish/publish_dzen.py --healthcheck
```

Healthcheck не открывает редактор и не доказывает авторизацию. Перед изменением статьи адаптер отдельно проверяет доступ к целевому каналу.

## Утверждённый выпуск

```text
python tools/publish_release.py prepare-dzen --release <release-dir>
python tools/publish_release.py schedule-dzen --release <release-dir>
python tools/publish_release.py check-dzen --release <release-dir>
```

Прямой вход: `python dzen-publish/publish_dzen.py --release <release-dir>`; независимая проверка — добавить `--check`. Материалы и расписание передаются через manifest и revision. Запуск без выпуска не публикует демонстрационный текст.

Внутри транспорта сохранены `fill_article`, упорядоченная последовательность, Word rich paste и отложка. Старые самостоятельные CLI-параметры статьи, `--media`, `--sequence` и `--schedule` больше не выполняют внешние изменения без контракта выпуска: используйте поля `dzen_article`, `dzen_images`, `dzen_sequence_path` и `scheduled_at` manifest.

Маршрут навыка: [публикация в Дзен](../docs/dzen-publication-route.md). Запуск идёт через общий CLI `tools/publish_release.py` (`prepare-dzen`, `schedule-dzen`, `check-dzen`). BDD-проверки, наблюдение очереди и тесты CDP находятся в ветке разработки `rework/publishing-solyanka`.
