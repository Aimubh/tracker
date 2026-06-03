"""
Scrapes top Amazon India search results for a given keyword.
Uses a single Playwright browser session for all pages.
"""

import asyncio
import re
from playwright.async_api import async_playwright, Browser


AMAZON_SEARCH_URL = "https://www.amazon.in/s?k={keyword}"


async def scrape_amazon(keyword: str, max_results: int = 5) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            results = await _run(browser, keyword, max_results)
        finally:
            await browser.close()
    return results


async def _run(browser: Browser, keyword: str, max_results: int) -> list[dict]:
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = await context.new_page()
    url = AMAZON_SEARCH_URL.format(keyword=keyword.replace(" ", "+"))
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(2000)

    cards = await page.query_selector_all("[data-component-type='s-search-result']")
    print(f"[Amazon] Found {len(cards)} cards")

    # Extract card data while page is still open (handles are tied to the page)
    raw_cards = []
    for card in cards[:max_results]:
        try:
            raw = await _extract_card_data(card)
            if raw:
                raw_cards.append(raw)
        except Exception as e:
            print(f"[Amazon] Card extract error: {e}")

    await page.close()

    # Now fetch individual product pages (page is closed, context still alive)
    products = []
    for raw in raw_cards:
        try:
            details = await _scrape_product_page(context, raw["url"]) if raw["url"] else {}
            description = details.get("description", "")
            keywords = _extract_keywords(raw["title"] + " " + description)
            products.append({**raw,
                "description": description,
                "description_word_count": len(description.split()),
                "image_count": details.get("image_count", 1),
                "bullet_count": details.get("bullet_count", 0),
                "keywords": keywords,
            })
            print(f"[Amazon] Done: {raw['title'][:60]}")
        except Exception as e:
            print(f"[Amazon] Product page error: {e}")

    await context.close()
    return products


async def _extract_card_data(card) -> dict | None:
    # Title — try multiple selectors
    title = ""
    for sel in ["h2 span.a-text-normal", "h2 a span", "[data-cy='title-recipe'] span", "h2 span"]:
        el = await card.query_selector(sel)
        if el:
            title = (await el.inner_text()).strip()
            if title:
                break
    if not title or title.lower() in ("sponsored", ""):
        return None

    # Price
    price = 0.0
    price_el = await card.query_selector(".a-price .a-offscreen")
    if price_el:
        price = _parse_price(await price_el.inner_text())

    # Rating
    rating = 0.0
    for sel in [".a-icon-star-small .a-icon-alt", "span.a-icon-alt", "[aria-label*='out of 5']"]:
        el = await card.query_selector(sel)
        if el:
            text = await el.get_attribute("aria-label") or await el.inner_text()
            rating = _parse_rating(text)
            if rating:
                break

    # Review count
    review_count = 0
    for sel in ["span[aria-label*='ratings']", ".a-size-small .a-link-normal", "span[aria-label]"]:
        el = await card.query_selector(sel)
        if el:
            label = await el.get_attribute("aria-label") or ""
            text = await el.inner_text()
            val = _parse_number(label or text)
            if val > 0:
                review_count = val
                break

    # Badge
    badge_el = await card.query_selector(".a-badge-label, .s-badge-text, span[data-csa-c-type='badge']")
    badge_text = (await badge_el.inner_text()).strip() if badge_el else ""
    has_best_seller = "best seller" in badge_text.lower()
    has_choice = "choice" in badge_text.lower()

    # Product URL
    link_el = await card.query_selector("h2 a, a.s-no-outline")
    href = await link_el.get_attribute("href") if link_el else ""
    product_url = "https://www.amazon.in" + href if href and href.startswith("/") else href

    return {
        "source": "amazon",
        "title": title,
        "price": price,
        "rating": rating,
        "review_count": review_count,
        "has_best_seller_badge": has_best_seller,
        "has_choice_badge": has_choice,
        "platform": "amazon",
        "url": product_url,
    }


async def _scrape_product_page(context, url: str) -> dict:
    """Opens product page in a new tab using the same context — no nested playwright."""
    if not url:
        return {}
    page = await context.new_page()
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        # Bullet points
        bullets = await page.query_selector_all("#feature-bullets li span.a-list-item")
        bullet_texts = []
        for b in bullets:
            t = (await b.inner_text()).strip()
            if t:
                bullet_texts.append(t)
        description = "\n".join(bullet_texts)

        # Images in alt-image carousel
        imgs = await page.query_selector_all("#altImages img, #imageBlock img")
        image_count = max(len(imgs), 1)

    except Exception as e:
        print(f"[Amazon] Product page error: {e}")
        description = ""
        image_count = 1
    finally:
        await page.close()

    return {
        "description": description,
        "bullet_count": len([l for l in description.splitlines() if l.strip()]),
        "image_count": image_count,
    }


def _parse_price(text: str) -> float:
    cleaned = text.replace(",", "").replace("₹", "").strip()
    m = re.search(r"[\d]+\.?\d*", cleaned)
    try:
        v = float(m.group()) if m else 0.0
        return v if v > 10 else 0.0
    except ValueError:
        return 0.0


def _parse_rating(text: str) -> float:
    m = re.search(r"(\d+\.?\d*)\s*out of", text)
    return float(m.group(1)) if m else 0.0


def _parse_number(text: str) -> int:
    cleaned = text.replace(",", "").replace(".", "")
    m = re.search(r"\d+", cleaned)
    return int(m.group()) if m else 0


def _extract_keywords(text: str) -> list[str]:
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                 "of", "with", "is", "it", "this", "that", "are", "by", "from",
                 "be", "as", "was", "has", "have", "our", "your", "its", "we"}
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:20]]


if __name__ == "__main__":
    results = asyncio.run(scrape_amazon("power bank", max_results=3))
    import json
    print(json.dumps(results, indent=2, ensure_ascii=False))
