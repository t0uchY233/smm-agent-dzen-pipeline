# dzen-publish

Автоматическая публикация статей на **Яндекс Дзен** через Chrome DevTools Protocol (CDP) + Playwright.

## Что делает скрипт

1. Подключается к Chrome по CDP (порт 9222) с таймаутом и безопасным повтором подключения
2. Открывает новую статью в редакторе Дзен
3. Заполняет заголовок и тело через буфер обмена
4. Обрабатывает диалог «Настройка канала» (принимает условия)
5. Публикует статью и возвращает ссылку

---

## Быстрый старт

### 1. Установить зависимости

```bash
pip install playwright
playwright install chromium
```

### 2. Запустить Chrome с CDP

Запустить `start_chrome.bat` (Windows). Он безопасно проверяет CDP и при необходимости открывает отдельный профиль Дзена, не закрывая обычные окна Chrome. Либо запустить Chrome вручную:

```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --remote-allow-origins=* ^
  --user-data-dir=C:\temp\chrome-cdp-profile ^
  "https://dzen.ru"
```

> ⚠️ При первом запуске нужно **залогиниться в Дзен** вручную в открывшемся Chrome.  
> Сессия сохраняется в `--user-data-dir` и больше не потребуется.

### 3. Настроить CHANNEL_URL

В файле `publish_dzen.py` найти строку:

```python
CHANNEL_URL = "https://dzen.ru/profile/editor/<CHANNEL_SLUG>"
```

Заменить на свой ID канала. Взять из URL редактора:
```
https://dzen.ru/profile/editor/id/<CHANNEL_ID>
```

### 4. Опубликовать статью

**Вариант A** — статья в файле:
```bash
python publish_dzen.py my_article.txt
```

Изображения можно прикрепить к статье через штатный диалог редактора:
```bash
python publish_dzen.py my_article.txt --media image.jpg image2.png
```
Поддерживаются PNG, JPEG, BMP, WebP и GIF. Перед публикацией скрипт ждёт загрузки превью и останавливается, если изображение не появилось в редакторе.

Отложенная публикация использует тот же CDP-путь, с московским временем:
```bash
python publish_dzen.py my_article.txt --media image.jpg image2.png --schedule 2026-09-24T14:00
```

Перед внешним действием можно отдельно проверить CDP без открытия редактора и без создания черновика:
```bash
python publish_dzen.py --healthcheck
```
Проверка завершается за ограниченное время; зависший WebSocket не оставляет процесс ждать бесконечно.

Формат файла `my_article.txt`:
```
Заголовок статьи

Первый абзац тела статьи.

Второй абзац.
```
(первая строка = заголовок, строка 2 пустая, дальше — тело)

**Вариант B** — статья прямо в скрипте:
```python
# Отредактировать TITLE и BODY в publish_dzen.py
TITLE = "Мой заголовок"
BODY  = """Текст статьи..."""
```
```bash
python publish_dzen.py
```

---

## Настройки

| Параметр | Где | Описание |
|----------|-----|----------|
| `CHANNEL_URL` | `publish_dzen.py` | полный адрес редактора канала Дзен |
| `--media` | командная строка | один или несколько локальных файлов изображений |
| `--schedule` | командная строка | время отложки `YYYY-MM-DDTHH:MM` в `Europe/Moscow` |
| `--healthcheck` | командная строка | только проверка CDP, без открытия редактора и публикации |
| `CDP_URL` | `publish_dzen.py` | Адрес CDP (по умолч. `http://127.0.0.1:9222`) |
| `--user-data-dir` | `start_chrome.bat` | Папка профиля Chrome (хранит сессию) |
| `--remote-debugging-port` | `start_chrome.bat` | Порт CDP |

---

## Как это работает технически

### Проблемы Дзен-редактора и их решения

| Проблема | Решение |
|----------|---------|
| `page.goto()` → `ERR_EMPTY_RESPONSE` | Навигация через `window.location.href` (SPA) |
| Body-поле не реагирует на `execCommand` | Вставка через буфер обмена (`Ctrl+V`) |
| Body CE исчезает после заполнения title | **Сначала вставляем тело**, потом заголовок |
| Title CE уходит за экран при прокрутке | `window.scrollTo(0,0)` перед кликом в title |
| Диалог «Настройка канала» блокирует публикацию | Автоматически: чекбокс + «Продолжить» |
| Диалог подтверждения публикации (y > 80) | Поиск кнопки «Опубликовать» с `y > 80` |
| DPR=1.25, координаты не совпадают | Все координаты в CSS px (viewport), не screen px |

### Структура редактора Дзен

```
[contenteditable][0]  ← заголовок  (cy ≈ 134, h=40)
[contenteditable][1]  ← тело       (cy ≈ 204, h=68)
```

Обе CE появляются при открытии пустого черновика. После вставки текста в body,
CE[0] (title) оказывается сверху, CE[1] уезжает вниз на высоту текста.

### Порядок действий в скрипте

```
1. goto dzen.ru (если нужно)
2. window.location → channel page
3. click (+) → 'Написать статью' → новый черновик URL
4. wait CE[0] + CE[1]
5. click CE[1] → Ctrl+V (вставляем BODY)
6. scrollTo(0,0)
7. click CE[0] → Ctrl+A → Ctrl+V (вставляем TITLE)
8. click 'Опубликовать' (header, y≈41)
9. handle modal: checkbox → 'Продолжить'
10. click 'Опубликовать' снова
11. handle confirm dialog (y > 80) → click
12. return final URL
```

---

## Структура файлов

```
dzen-publish/
├── publish_dzen.py      # основной скрипт (переиспользуемый)
├── start_chrome.bat     # запуск Chrome с CDP
├── article_template.txt # шаблон формата статьи
└── README.md
```

---

## Требования

- Windows 10/11
- Python 3.10+
- Google Chrome
- `playwright` (`pip install playwright && playwright install chromium`)

---

## Первая настройка (один раз)

1. Запустить `start_chrome.bat`
2. В открывшемся Chrome зайти в аккаунт Дзен
3. Убедиться что канал создан (или создать его в редакторе)
4. Взять CHANNEL_ID из URL и вставить в `publish_dzen.py`
5. Закрыть Chrome

После этого Chrome запоминает сессию — каждый следующий запуск уже авторизован.
