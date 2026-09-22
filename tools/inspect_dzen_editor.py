"""Read-only CDP inspection of the current Dzen editor DOM for troubleshooting."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright


async def main(url):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = next((p for p in context.pages if p.url.startswith(url)), None)
        if page is None:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(1000)
        payload = await page.evaluate("""
        () => ({
          url: location.href,
          editors: Array.from(document.querySelectorAll('[contenteditable]')).map((node, index) => ({
            index,
            visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
            text: (node.innerText || '').slice(0, 140),
            className: node.className,
            testId: node.getAttribute('data-testid'),
            outer: node.outerHTML.slice(0, 500)
          })),
          images: Array.from(document.querySelectorAll('[data-testid="article-image-item"]')).map((node, index) => ({
            index,
            outer: node.outerHTML.slice(0, 1500),
            figure: node.closest('figure') ? node.closest('figure').outerHTML.slice(0, 5000) : '',
            controls: node.closest('figure') ? Array.from(node.closest('figure').querySelectorAll('button, [role="button"]')).map(button => ({
              text: (button.innerText || '').trim(), tip: button.getAttribute('data-tip'),
              aria: button.getAttribute('aria-label'), title: button.getAttribute('title'),
              outer: button.outerHTML.slice(0, 800)
            })) : []
          })),
          buttons: Array.from(document.querySelectorAll('button')).map(node => ({
            text: (node.innerText || '').trim(), tip: node.getAttribute('data-tip'),
            aria: node.getAttribute('aria-label')
          })).filter(item => item.tip || /удал|изобр/i.test(item.text + ' ' + item.aria)),
          allButtons: Array.from(document.querySelectorAll('button, [role="button"]')).map(node => ({
            text: (node.innerText || '').trim(), tip: node.getAttribute('data-tip'),
            aria: node.getAttribute('aria-label'), title: node.getAttribute('title'),
            className: node.className
          })).filter(item => item.text || item.tip || item.aria || item.title),
          dialogs: Array.from(document.querySelectorAll('[role="dialog"], [class*="modal"]')).map(node => ({
            text: (node.innerText || '').slice(0, 800),
            visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
            outer: node.outerHTML.slice(0, 1200)
          })),
          removal: Array.from(document.querySelectorAll('div[class*="removeButton"]')).map(node => {
            const rect = node.getBoundingClientRect();
            const point = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
            return {rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height},
              point: point ? {tag: point.tagName, className: point.className} : null};
          }),
          bodyBlocks: (() => {
            const root = Array.from(document.querySelectorAll('[contenteditable]')).find(node =>
              node.getAttribute('aria-describedby') === 'placeholder-ZenDraftEditor');
            const contents = root ? root.querySelector('[data-contents="true"]') : null;
            return contents ? Array.from(contents.children).map((node, index) => ({
              index,
              tag: node.tagName,
              className: node.className,
              text: (node.innerText || '').trim().slice(0, 120),
              image: !!node.querySelector('[data-testid="article-image-item"]')
            })) : [];
          })()
        })
        """)
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
