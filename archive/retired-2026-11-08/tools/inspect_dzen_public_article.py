"""Read-only inspection of a Dzen article or scheduled article page over CDP."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright


async def main(url):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(1500)
        result = await page.evaluate("""
        () => ({
          url: location.href,
          text: (document.body.innerText || '').slice(0, 12000),
          imageCount: document.images.length,
          title: document.title
        })
        """)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(sys.argv[1]))
