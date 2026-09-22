---
name: render-with-visuals
description: Use when a raw talking-head MP4 should be converted into a final MP4 with automatic visual cards/slides overlaid before upload to YouTube
---

# Render With Visuals

## Overview

Локальный шаг `1.5` между записью и загрузкой на YouTube. Шеф записывает raw-видео по DOCX-телесуфлёру без листания слайдов. Этот skill генерирует карточки из DOCX, синхронизирует их с речью локальным Whisper `large-v3` и собирает финальный MP4 через `tools/render_video_visuals.py`.

После рендера следующий шаг — `/publish-from-script "<output_video>" --docx "<docx_path>"` для прямой загрузки на YouTube.

## Requirements

Перед подготовкой визуалов прочитать [общие правила визуального стиля](../video-script/references/visual-style.md) и посмотреть сохранённый референс: белый фон, крупная чёрно-красная типографика, предметная иллюстрация, заметные цифры; таблицы — с читаемыми колонками и красным выделением итога. Не выводить `VISUAL`, тип карточки или другую служебную метку. Для новых схем использовать встроенную генерацию по правилам `video-script`; простые локальные текстовые карточки допустимы лишь как явно согласованный технический резерв, а не как финальные визуалы этого стиля.

- Локальный runtime устанавливает `faster-whisper`; внешние ASR-ключи не нужны.
- В системе доступен `ffmpeg`.
- DOCX лежит в `.tmp/teleprompter/YYYY-MM-DD-HHMM-Русский заголовок.docx`.
- Raw MP4 желательно назвать тем же basename: `YYYY-MM-DD-HHMM-Русский заголовок.mp4`.

## Embedded DOCX Visual Guard

If the DOCX contains embedded files under `word/media/*`, do not continue with generated text-card mode. Use `render-docx-visuals` instead.

In DOCX visual mode, `embedded_images` only proves extraction. It does not prove that charts, dashboards, schemes, screenshots, and tables reached the rendered video. After every render, compare:

- all `slides[].id` values in `embedded_visual_plan.json`;
- all `slide_id` values in `timeline.json`.

Every `docx_visual_*` from the slide plan must appear in the timeline. If any are missing, treat the render as failed, fix timing/anchor handling, and re-render before reporting success.

## Workflow

1. Получить путь к raw MP4.
2. Если пользователь явно передал DOCX — использовать его. Иначе искать `.tmp/teleprompter/<video-stem>.docx`.
3. Запустить:
   ```bash
   python3 tools/render_video_visuals.py "<raw_mp4>" --force
   ```
4. Если нужно проверить план и таймлайн без транскрибации и финального рендера:
   ```bash
   python3 tools/render_video_visuals.py "<raw_mp4>" --dry-run
   ```
5. Показать пользователю JSON-результат: `output_video`, `slide_plan`, `timeline`, `asr_matches`, `fallback_matches`.
6. Сказать, что на YouTube нужно загрузить `output_video`, не raw-файл.

## Output Contract

Артефакты:

```text
.tmp/visuals/<base>/slide_plan.json
.tmp/visuals/<base>/transcript.json
.tmp/visuals/<base>/timeline.json
.tmp/visuals/<base>/slide_001.png
.tmp/rendered/<base>.mp4
```

`<base>` должен совпадать с `YYYY-MM-DD-HHMM-Русский заголовок`: время в имени задаёт план публикации на YouTube в МСК.

## Failure Handling

| Ошибка | Действие |
|---|---|
| DOCX не найден | Попросить пользователя передать `--docx <path>` |
| Whisper не распознал часть якорей | Продолжить: timeline использует fallback по позиции текста |
| Whisper `large-v3` не запускается на GPU | Повторить локально на CPU с `int8` |
| FFmpeg упал | Показать stderr и не загружать raw на YouTube |

## Common Mistakes

- Не загружать raw MP4 на YouTube после появления этого шага.
- Сохранять имя rendered-файла: `YYYY-MM-DD-HHMM-Русский заголовок.mp4`.
- Не ставить слайды вручную во время записи: вся синхронизация делается после записи.
