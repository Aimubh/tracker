"""
Scrapes your own product from lazerbelieve.com using Playwright.
"""

import asyncio
import re
from playwright.async_api import async_playwright


YOUR_PRODUCT_URL = "https://www.lazerbelieve.com/products/lazer-magsleek-20w-5000-mah-power-bank"


async def scrape_your_product(url: str = YOUR_PRODUCT_URL) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=30000)
        await page.wait_for_timeout(2000)

        title = await _get_text(page, "h1")
        sale_price = await _extract_product_price(page)

        # Real description lives in .rte (rich text editor block)
        description = await _get_text(page, ".rte")

        # Images — scoped to product media section
        images = await page.query_selector_all(".m-product-media img, [class*='product-media'] img")
        # Deduplicate by src
        seen = set()
        unique_images = []
        for img in images:
            src = await img.get_attribute("src") or ""
            if src and src not in seen:
                seen.add(src)
                unique_images.append(img)
        image_count = len(unique_images)

        await browser.close()

    keywords = _extract_keywords(title + " " + description)

    # Count bullet points from description (lines starting with common markers)
    bullet_count = len([
        l for l in description.splitlines()
        if l.strip() and (l.strip().startswith(("-", "•", "*", "✓", "→")) or len(l.strip()) < 80)
    ])

    return {
        "source": "lazerbelieve.com",
        "title": title.strip() if title else "Lazer MagSleek 20W 5000 mAh Power Bank",
        "price": sale_price,
        "description": description.strip() if description else "",
        "description_word_count": len((description or "").split()),
        "image_count": image_count,
        "rating": None,
        "review_count": 0,
        "keywords": keywords,
        "bullet_count": bullet_count,
        "has_best_seller_badge": False,
        "platform": "website",
    }


async def _get_text(page, selector: str) -> str:
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.inner_text()
    except Exception:
        pass
    return ""


async def _extract_product_price(page) -> float:
    """Scope to the main product price block to avoid picking up other product prices."""
    el = await page.query_selector(".main-product__block-price, .main-product__block.main-product__block-price")
    if el:
        text = (await el.inner_text()).strip()
        after_label = re.split(r"sale price", text, flags=re.IGNORECASE, maxsplit=1)[-1]
        price = _parse_price_text(after_label)
        if price > 100:
            return price

    # Fallback: any price block with "Sale price" where first number > 500
    els = await page.query_selector_all("[class*='price']")
    for el in els:
        text = (await el.inner_text()).strip()
        if "sale price" in text.lower():
            after_label = re.split(r"sale price", text, flags=re.IGNORECASE, maxsplit=1)[-1]
            price = _parse_price_text(after_label)
            if price > 500:
                return price

    return 0.0


def _parse_price_text(text: str) -> float:
    cleaned = text.replace(",", "").replace("Rs.", "").replace("₹", "")
    nums = re.findall(r"\d+\.?\d*", cleaned)
    for n in nums:
        v = float(n)
        if v > 100:
            return v
    return 0.0


def _extract_keywords(text: str) -> list[str]:
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                 "of", "with", "is", "it", "this", "that", "are", "by", "from",
                 "be", "as", "was", "has", "have", "our", "your", "its", "we",
                 "you", "can", "also", "all", "any", "not", "get", "use", "will"}
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:20]]


if __name__ == "__main__":
    result = asyncio.run(scrape_your_product())
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
