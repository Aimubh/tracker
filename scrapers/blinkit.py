"""
Blinkit scraper — intercepts the v1/layout/search API response.
Blinkit's product data is in response.snippets[].data (name, mrp, image, variant).
"""

import asyncio
import re
import json as json_lib
from playwright.async_api import async_playwright, Response


BLINKIT_SEARCH_URL = "https://blinkit.com/s/?q={keyword}"


async def scrape_blinkit(keyword: str, max_results: int = 5) -> list[dict]:
    try:
        captured_snippets = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--window-position=-32000,-32000",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            await context.grant_permissions(["geolocation"])
            await context.set_geolocation({"latitude": 19.0760, "longitude": 72.8777})
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
            )

            page = await context.new_page()

            async def handle_response(response: Response):
                if "layout/search" in response.url:
                    try:
                        data = await response.json()
                        snippets = data.get("response", {}).get("snippets", [])
                        captured_snippets.extend(snippets)
                        print(f"[Blinkit] API captured {len(snippets)} snippets from {response.url[:70]}")
                    except Exception:
                        pass

            page.on("response", handle_response)

            # Load homepage first for location cookie
            try:
                await page.goto("https://blinkit.com", timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Load search — triggers the API call
            url = BLINKIT_SEARCH_URL.format(keyword=keyword.replace(" ", "+"))
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[Blinkit] Navigation error (continuing): {e}")

            await page.wait_for_timeout(5000)
            await browser.close()

        products = _parse_snippets(captured_snippets, max_results)
        print(f"[Blinkit] Extracted {len(products)} products")
        return products

    except Exception as e:
        print(f"[Blinkit] Scrape failed: {e}")
        return []


def _text(field) -> str:
    """Blinkit API fields are objects like {'text': '...', 'color': ...}."""
    if isinstance(field, dict):
        return str(field.get("text") or "").strip()
    return str(field or "").strip()


def _parse_snippets(snippets: list, max_results: int) -> list[dict]:
    products = []
    for snippet in snippets:
        data = snippet.get("data", {})

        name = _text(data.get("name"))
        if not name or len(name) < 3:
            continue

        # Price — strip currency symbol and commas from text
        price = 0.0
        for price_key in ("mrp", "normal_price", "price", "discounted_price"):
            raw = _text(data.get(price_key))
            if raw:
                cleaned = re.sub(r"[^\d.]", "", raw)
                try:
                    price = float(cleaned)
                    break
                except ValueError:
                    pass

        variant = _text(data.get("variant"))
        image = data.get("image", {}) or {}
        image_url = image.get("url", "") if isinstance(image, dict) else ""

        # Product URL from click_action
        click_action = data.get("click_action", {}) or {}
        action_data = click_action.get("data", {}) if isinstance(click_action, dict) else {}
        slug = action_data.get("slug", "") if isinstance(action_data, dict) else ""
        product_url = f"https://blinkit.com/prn/{slug}" if slug else ""

        keywords = _extract_keywords(name + " " + variant)

        products.append({
            "source": "blinkit",
            "title": name,
            "price": price,
            "description": variant,
            "description_word_count": len(variant.split()),
            "image_count": 1 if image_url else 0,
            "bullet_count": 0,
            "rating": 0.0,
            "review_count": 0,
            "keywords": keywords,
            "has_best_seller_badge": False,
            "has_choice_badge": False,
            "platform": "blinkit",
            "url": product_url,
        })

        if len(products) >= max_results:
            break

    return products


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
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    results = asyncio.run(scrape_blinkit("travel bottle", max_results=5))
    print(json_lib.dumps(results, indent=2, ensure_ascii=False))
