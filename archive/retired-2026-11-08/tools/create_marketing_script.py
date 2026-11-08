"""Create the approved teleprompter DOCX and fallback analytical visuals."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
BASE = '2026-09-24-1400-Бутылочное горлышко в маркетинге'
DOCX = ROOT / '.tmp' / 'teleprompter' / f'{BASE}.docx'
ASSETS = ROOT / '.tmp' / 'teleprompter' / f'{BASE}_assets'


def font(size=34, bold=False):
    candidates = [
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\segoeui.ttf',
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap(draw, text, f, width):
    words, lines, current = text.split(), [], ''
    for word in words:
        candidate = (current + ' ' + word).strip()
        if draw.textbbox((0, 0), candidate, font=f)[2] > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def visual(name, title, blocks, accent='#CDDFF2'):
    image = Image.new('RGB', (1600, 900), 'white')
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = font(46, True), font(32), font(25)
    draw.text((80, 65), title, fill='#252525', font=title_font)
    y = 190
    for index, (label, text) in enumerate(blocks):
        x = 100 + (index % 2) * 690
        if index and index % 2 == 0:
            y += 235
        top = y + (index % 2) * 0
        draw.rounded_rectangle((x, top, x + 570, top + 170), radius=18, fill=accent if index == 1 else '#F7F8FA', outline='#B7BEC8', width=3)
        draw.text((x + 28, top + 24), label, fill='#202020', font=font(29, True))
        lines = wrap(draw, text, body_font, 510)
        for line_no, line in enumerate(lines[:3]):
            draw.text((x + 28, top + 78 + line_no * 38), line, fill='#30343B', font=body_font)
    image.save(ASSETS / name, quality=95)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill)
    tc_pr.append(shd)


def add_text(doc, text, style=None):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.line_spacing = 1.4
    p.add_run(text)
    return p


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    visual('01-цепочка.png', 'Где теряется путь к оплате', [
        ('Реклама', 'показы и бюджет'), ('Заявка', 'контакт с компанией'),
        ('Целевой клиент', 'подходит по задаче'), ('Предложение', 'понятная ценность'),
        ('Оплата', 'деньги на счёте'),
    ], '#EFD0C9')
    visual('02-экономика.png', 'Исходная экономика привлечения', [
        ('Реклама', '300 000 ₽ за месяц'), ('Все заявки', '100 контактов'),
        ('Целевые', '20 подходящих компаний'), ('Договоры', '5 оплат'),
        ('Расчёт', '3 000 ₽ за заявку; 60 000 ₽ на договор'),
    ], '#F1E0BD')
    visual('03-сравнение.png', 'Два расчётных варианта', [
        ('Больше бюджета', '600 000 ₽ → 10 договоров'), ('Точнее предложение', '300 000 ₽ → 8 договоров'),
        ('Стоимость договора', '60 000 ₽ против 37 500 ₽'), ('Допущение', 'учебная модель, не прогноз'),
    ], '#CDE5DA')
    visual('04-эксперимент.png', 'Один эксперимент вместо смены всего маркетинга', [
        ('1', 'разбери последние 30 заявок'), ('2', 'выбери один сегмент'),
        ('3', 'сравни одинаковые условия'), ('4', 'дождись оплат и посчитай'),
    ], '#CDDFF2')

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.8); section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.95); section.right_margin = Inches(0.95)
    normal = doc.styles['Normal']
    normal.font.name = 'Arial'; normal.font.size = Pt(16)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('Бутылочное горлышко в маркетинге: почему больше рекламы не даёт больше продаж')
    run.bold = True; run.font.name = 'Arial'; run.font.size = Pt(22)
    meta = doc.add_paragraph('Публикация: 2026-09-24 14:00 MSK')
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.runs[0].font.color.rgb = RGBColor(110, 110, 110)
    meta.runs[0].font.size = Pt(10)

    sections = [
        ('Хук', 'Ты увеличил рекламный бюджет. Заявок стало больше, менеджеры загружены, а денег почти не прибавилось. Знакомая ситуация? Тогда не покупай следующий лид, пока не найдёшь участок, который ограничивает оплату.'),
        ('Тезис', 'Маркетинг — это не кнопка «привести клиента». Это цепочка: реклама, заявка, подходящий клиент, предложение, оплата. Если ограничение находится между заявкой и продажей, дополнительная реклама просто увеличит очередь и нагрузку на менеджеров.'),
        ('Теория', 'Обычно руководитель смотрит на самый низкий процент и сразу объявляет его бутылочным горлышком. Это ошибка. Низкая конверсия может быть нормальным фильтром. Ограничение — это участок, который не даёт системе получить больше оплаченных заказов и при этом забирает ресурс: время менеджеров, бюджет или внимание руководителя.'),
        ('Кейс', 'Разберём учебный B2B-пример. Компания продаёт услуги промышленным предприятиям. За месяц она потратила на рекламу 300 000 рублей и получила 100 заявок. Только 20 компаний подходили по отрасли, масштабу и задаче. В итоге заключили 5 договоров. Реклама на один договор — 60 000 рублей. Это расчёт учебной модели, а не обещание результата.'),
        ('Кейс: где искать потери', 'Первые вопросы простые. Почему 80 заявок не стали целевыми? Обещание в рекламе слишком широкое? Не тот сегмент? Менеджер не успевает квалифицировать заявки? Предложение сформулировано языком компании, а не языком покупателя? Пока эти причины не проверены, увеличение бюджета — ставка вслепую.'),
        ('Сравнение', 'Теперь сравним два расчётных варианта. В первом компания удваивает бюджет до 600 000 рублей и получает 200 заявок. Если доли не меняются, целевых будет 40, а договоров — 10. Реклама на договор останется 60 000 рублей. Во втором варианте бюджет остаётся 300 000 рублей, но предложение точнее: 80 заявок, 32 целевые и 8 договоров. Реклама на договор — 37 500 рублей. Это не прогноз. Это способ увидеть, какие допущения управляют расчётом.'),
        ('Практика', 'Открой последние 30 заявок. Для каждой отметь источник, сегмент, задачу, результат квалификации, причину отказа и время первого ответа. Затем выбери один сегмент. Не пять. Один. Сформулируй одну гипотезу: например, что руководители производственных компаний лучше реагируют на расчёт потерь, чем на общее обещание роста.'),
        ('Эксперимент', 'Сравни две версии предложения при одинаковом бюджете и одинаковом сроке. Не меняй одновременно рекламу, скрипт, сайт и работу менеджеров. Иначе ты не узнаешь, что сработало. Смотри не на клики, а на оплаченные договоры и маржинальный доход после расходов на привлечение.'),
        ('Резюме', 'Три вывода. Первый: больше заявок не равно больше денег. Второй: низкая конверсия требует проверки причин, а не автоматического увеличения бюджета. Третий: один измеримый эксперимент полезнее, чем одновременная переделка всего маркетинга.'),
        ('Финал', 'Открой последние 30 заявок. Отметь, кто подходит, кто купил и почему остальные остановились. Найди участок, который действительно ограничивает оплату. И только после этого решай, нужен ли тебе следующий рекламный бюджет.'),
    ]
    image_map = {3: '01-цепочка.png', 4: '02-экономика.png', 5: '03-сравнение.png', 7: '04-эксперимент.png'}
    for i, (heading, text) in enumerate(sections):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(12)
        r = h.add_run(heading); r.bold = True; r.font.size = Pt(18)
        add_text(doc, text)
        if i in image_map:
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(ASSETS / image_map[i]), width=Inches(6.45))
    doc.save(DOCX)
    print(DOCX)
    print('ASSETS', ASSETS)


if __name__ == '__main__':
    main()
