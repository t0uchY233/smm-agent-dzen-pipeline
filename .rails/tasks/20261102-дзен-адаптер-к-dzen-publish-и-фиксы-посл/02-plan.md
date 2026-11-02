# План: Дзен — адаптер к dzen-publish и фиксы после реальной публикации

## Шаги
- [x] S1: транспорт — wip-версия publish_dzen.py, совмещённая с open_channel() из issue-2-auth; README/.gitignore из wip; ensure_cdp_chrome.ps1 из issue-2-auth — файлы: dzen-publish/publish_dzen.py, dzen-publish/README.md, dzen-publish/.gitignore, dzen-publish/ensure_cdp_chrome.ps1
- [x] S2: CDP-хелпер из issue-2-auth и контент-контракт из wip, image_occurrences перенести в dzen_content — файлы: tools/chrome_cdp.py, tools/dzen_content.py
- [x] S3: адаптер выпуска из wip без зависимости от render_qa — файлы: tools/publishing_dzen.py
- [x] S4: подготовка DOCX-последовательности из wip — файлы: tools/extract_docx_dzen_sequence.py, tools/copy_docx_body_to_clipboard.ps1
- [x] S5: ревизия учитывает последовательность, её изображения и футер; CLI prepare-dzen/schedule-dzen/check-dzen — файлы: tools/publishing_core.py, tools/publish_release.py
- [x] S6: тесты — BDD Дзена и наблюдения из wip, изоляция сети/переменных, тесты chrome_cdp из PR, pytest.ini — файлы: tests/__init__.py, tests/bdd/**, conftest.py, pytest.ini, tools/test_chrome_cdp.py
- [x] S7: описание вендора — ссылки «переносится в T4» заменить фактическими — файлы: dzen-publish/UPSTREAM.md

## Границы
Не трогаем: core-монтаж и `tools/render_qa.py` (не переносим), YouTube/Telegram-адаптеры (T2/T3), навыки `dzen`/`publish-from-script`/`smm-conductor`, `docs/` и спецификацию (T5), `.env`, `.local/auth/`, профили Chrome. Никаких запусков против живого dzen.ru.

## Параллелизация
Последовательно: S3 зависит от S1–S2, S5–S6 от S3; исполнитель один (Pi). Claude параллельно ждёт тестовый слот и готовит T5.

## Ревью
Pi в чистом контексте ревьюит дифф против wip и issue-2-auth (что перенесено, что намеренно нет), проверяет отсутствие render_qa и безопасность CDP. Claude — гейты, дифф, прогон под codex-test-guard. Human review: read-only `check-dzen` на существующей статье и реальная отложка — отдельная приёмка с разрешения пользователя.
