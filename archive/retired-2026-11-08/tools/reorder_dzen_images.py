"""Place Dzen image blocks before the following source paragraph via native drag/drop."""
import asyncio, sys
from playwright.async_api import async_playwright

ANCHORS = [
    "Разберем один условный завод", "У нашего завода продажи", "На условном заводе купили станок",
    "На нашем заводе есть любимый клиент", "У завода может быть прибыльный заказ",
    "На складе завода семь лет лежит деталь", "Если очередь стоит перед покраской",
    "Распоряжение «снизим цену", "Для каждого показателя нужны формула", "Проверяем итоговые суммы",
]

async def main(url, limit):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = next((x for x in browser.contexts[0].pages if x.url.startswith(url)), None)
        if page is None:
            page = await browser.contexts[0].new_page(); await page.goto(url, wait_until="domcontentloaded")
        for anchor in ANCHORS[:limit]:
            image = page.locator('figure[data-editor="ZenDraftEditor"]').first
            target = page.locator('div.zen-editor-block-paragraph[data-editor="ZenDraftEditor"]').filter(has_text=anchor).first
            if await image.count() == 0 or await target.count() == 0:
                raise RuntimeError(f"Не найден блок для якоря: {anchor}")
            await image.scroll_into_view_if_needed(); await target.scroll_into_view_if_needed()
            await image.drag_to(target, timeout=15000)
            await page.wait_for_timeout(800)
            order = await page.evaluate("""anchor => {
              const nodes = [...document.querySelectorAll('[data-editor="ZenDraftEditor"][data-block="true"]')];
              const target = nodes.find(n => n.tagName === 'DIV' && n.innerText.startsWith(anchor));
              const previous = target && nodes[nodes.indexOf(target)-1];
              return !!previous && previous.tagName === 'FIGURE';
            }""", anchor)
            if not order: raise RuntimeError(f"Dzen не подтвердил перенос изображения перед: {anchor}")
            print(f"Placed image before: {anchor}")

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv)>2 else 10))
