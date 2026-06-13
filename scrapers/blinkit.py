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

        # Product URL from click_action blinkit_deeplink (grofers://pdp?product_id=...)
        product_url = ""
        click_action = data.get("click_action", {}) or {}
        if isinstance(click_action, dict):
            deeplink = click_action.get("blinkit_deeplink", {}) or {}
            deeplink_url = deeplink.get("url", "") if isinstance(deeplink, dict) else str(deeplink)
            m = re.search(r"product_id=(\d+)", deeplink_url)
            if m:
                product_url = f"https://blinkit.com/prn/prid/{m.group(1)}"

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


async def scrape_our_blinkit_listing(url: str) -> dict:
    """
    Scrapes our own Blinkit listing page to get title, price, images, and description.
    URL format: https://blinkit.com/prn/prid/{product_id}
    """
    if not url:
        return {}
    try:
        captured_product = {}

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

            # Intercept product API responses
            async def handle_response(response):
                if "product" in response.url and "layout" in response.url:
                    try:
                        data = await response.json()
                        snippets = data.get("response", {}).get("snippets", [])
                        for s in snippets:
                            d = s.get("data", {})
                            name = _text(d.get("name"))
                            if name:
                                captured_product.update(d)
                                break
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                await page.goto("https://blinkit.com", timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
            except Exception:
                pass

            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[Blinkit OurListing] Navigation error: {e}")

            await page.wait_for_timeout(4000)

            # Scrape the product page DOM directly
            title = ""
            price = 0.0
            image_urls = []
            description = ""

            # Title
            for sel in ["h1", "[class*='product-name']", "[class*='ProductName']"]:
                el = await page.query_selector(sel)
                if el:
                    t = (await el.inner_text()).strip()
                    if t and len(t) > 2:
                        title = t
                        break

            # Price
            for sel in ["[class*='price']", "[class*='Price']"]:
                el = await page.query_selector(sel)
                if el:
                    raw = (await el.inner_text()).strip()
                    cleaned = re.sub(r"[^\d.]", "", raw)
                    try:
                        v = float(cleaned)
                        if v > 0:
                            price = v
                            break
                    except ValueError:
                        pass

            # Images
            img_els = await page.query_selector_all("img[src*='cdn']")
            for img in img_els:
                src = await img.get_attribute("src") or ""
                if src and "product" in src and src not in image_urls:
                    image_urls.append(src)

            # Description
            for sel in ["[class*='description']", "[class*='Description']", "[class*='detail']"]:
                el = await page.query_selector(sel)
                if el:
                    t = (await el.inner_text()).strip()
                    if t:
                        description = t
                        break

            # Fallback: use captured API data
            if not title and captured_product:
                title = _text(captured_product.get("name", ""))
                for pk in ("mrp", "normal_price", "price"):
                    raw = _text(captured_product.get(pk, ""))
                    if raw:
                        cleaned = re.sub(r"[^\d.]", "", raw)
                        try:
                            price = float(cleaned)
                            break
                        except ValueError:
                            pass
                img = captured_product.get("image", {}) or {}
                if isinstance(img, dict) and img.get("url"):
                    image_urls = [img["url"]]

            await browser.close()

        main_image_url = image_urls[0] if image_urls else ""
        result = {
            "source": "blinkit_ours",
            "platform": "blinkit",
            "title": title,
            "url": url,
            "price": price,
            "rating": 0.0,
            "review_count": 0,
            "description": description,
            "description_word_count": len(description.split()),
            "bullet_count": 0,
            "image_count": len(image_urls),
            "image_urls": image_urls,
            "main_image_url": main_image_url,
            "keywords": _extract_keywords(title + " " + description),
            "has_best_seller_badge": False,
        }
        print(f"[Blinkit OurListing] Scraped: {title[:60]} | {len(image_urls)} images | ₹{price}")
        return result

    except Exception as e:
        print(f"[Blinkit OurListing] Failed: {e}")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    results = asyncio.run(scrape_blinkit("travel bottle", max_results=5))
    print(json_lib.dumps(results, indent=2, ensure_ascii=False))
