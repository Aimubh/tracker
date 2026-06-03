"""
Discovers all products from lazerbelieve.com and scrapes each product page.
"""

import asyncio
import re
from playwright.async_api import async_playwright

BASE_URL = "https://www.lazerbelieve.com"
STORE_URL = f"{BASE_URL}/"


async def get_all_products() -> list[dict]:
    """Scrape the homepage to discover all products, then scrape each product page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # Step 1: Discover product URLs from homepage
        page = await context.new_page()
        await page.goto(STORE_URL, timeout=30000)
        await page.wait_for_timeout(2000)

        links = await page.query_selector_all("a[href*='/products/']")
        seen = set()
        product_urls = []
        for link in links:
            href = await link.get_attribute("href")
            if href and "/products/" in href:
                full = BASE_URL + href if href.startswith("/") else href
                # strip query params
                full = full.split("?")[0]
                if full not in seen:
                    seen.add(full)
                    product_urls.append(full)

        await page.close()
        print(f"[Catalog] Found {len(product_urls)} product URLs")

        # Step 2: Scrape each product page
        products = []
        for url in product_urls:
            try:
                product = await _scrape_product(context, url)
                if product:
                    products.append(product)
                    print(f"[Catalog] Scraped: {product['title']} | ₹{product['price']}")
            except Exception as e:
                print(f"[Catalog] Failed {url}: {e}")

        await browser.close()

    return products


async def _scrape_product(context, url: str) -> dict | None:
    page = await context.new_page()
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        # Title
        title_el = await page.query_selector("h1")
        title = (await title_el.inner_text()).strip() if title_el else ""
        if not title:
            return None

        # Sale price — scoped to main product block
        price = await _extract_price(page)

        # Description from .rte block
        desc_el = await page.query_selector(".rte")
        description = (await desc_el.inner_text()).strip() if desc_el else ""

        # Images — deduplicated
        imgs = await page.query_selector_all(".m-product-media img, [class*='product-media'] img")
        seen_src = set()
        image_count = 0
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if src and src not in seen_src:
                seen_src.add(src)
                image_count += 1

        # Category from breadcrumb or URL
        category = _extract_category(url)

        # Bullet-like lines in description
        bullet_count = len([
            l for l in description.splitlines()
            if l.strip() and len(l.strip()) < 100
        ])

        keywords = _extract_keywords(title + " " + description)

        # Auto-generate Amazon search keyword from title
        amazon_keyword = _make_search_keyword(title)

    finally:
        await page.close()

    return {
        "title": title,
        "url": url,
        "price": price,
        "description": description,
        "description_word_count": len(description.split()),
        "image_count": image_count,
        "bullet_count": bullet_count,
        "rating": None,
        "review_count": 0,
        "keywords": keywords,
        "category": category,
        "amazon_keyword": amazon_keyword,
        "has_best_seller_badge": False,
        "platform": "website",
        "source": "lazerbelieve.com",
    }


async def _extract_price(page) -> float:
    el = await page.query_selector(".main-product__block-price, .main-product__block.main-product__block-price")
    if el:
        text = (await el.inner_text()).strip()
        after = re.split(r"sale price", text, flags=re.IGNORECASE, maxsplit=1)[-1]
        price = _parse_price(after)
        if price > 0:
            return price

    els = await page.query_selector_all("[class*='price']")
    for el in els:
        text = (await el.inner_text()).strip()
        if "sale price" in text.lower():
            after = re.split(r"sale price", text, flags=re.IGNORECASE, maxsplit=1)[-1]
            price = _parse_price(after)
            if price > 50:
                return price
    return 0.0


def _parse_price(text: str) -> float:
    cleaned = text.replace(",", "").replace("Rs.", "").replace("₹", "")
    for n in re.findall(r"\d+\.?\d*", cleaned):
        v = float(n)
        if v > 50:
            return v
    return 0.0


def _extract_category(url: str) -> str:
    slug = url.rstrip("/").split("/products/")[-1]
    words = slug.replace("-", " ").split()
    # Skip brand name "lazer" at start
    if words and words[0].lower() == "lazer":
        words = words[1:]
    return " ".join(words[:4]).title()


def _make_search_keyword(title: str) -> str:
    """Generate a good Amazon search keyword from the product title."""
    # Remove brand name and common filler words
    stopwords = {"lazer", "pure", "mini", "new", "the", "a", "an", "and", "in", "for",
                 "with", "of", "1", "set", "ml", "inch", "kit"}
    words = re.findall(r"\b[a-zA-Z0-9]+\b", title.lower())
    filtered = [w for w in words if w not in stopwords]
    return " ".join(filtered[:5])


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
    import json
    products = asyncio.run(get_all_products())
    print(json.dumps([{"title": p["title"], "price": p["price"], "amazon_keyword": p["amazon_keyword"]} for p in products], indent=2))
