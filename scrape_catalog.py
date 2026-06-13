"""
Background scraper: enriches product_catalog.json with real titles, prices,
ratings, images from Amazon and Blinkit pages.

Run once: python scrape_catalog.py
Re-run anytime to pick up where it left off (skips already-scraped entries).
Progress is saved after every 5 products so interruption is safe.
"""

import asyncio
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

AMAZON_PATH  = os.path.join(os.path.dirname(__file__), "amazon_catalog.json")
BLINKIT_PATH = os.path.join(os.path.dirname(__file__), "blinkit_catalog.json")


def load_catalog() -> dict:
    with open(AMAZON_PATH,  "r", encoding="utf-8") as f:
        amazon = json.load(f)
    with open(BLINKIT_PATH, "r", encoding="utf-8") as f:
        blinkit = json.load(f)
    return {"amazon": amazon, "blinkit": blinkit}


def save_catalog(catalog: dict):
    with open(AMAZON_PATH,  "w", encoding="utf-8") as f:
        json.dump(catalog["amazon"],  f, indent=2, ensure_ascii=False)
    with open(BLINKIT_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog["blinkit"], f, indent=2, ensure_ascii=False)


# ── Amazon scraper ─────────────────────────────────────────────────────────────

async def scrape_amazon_titles(catalog: dict):
    from playwright.async_api import async_playwright

    entries = [e for e in catalog["amazon"] if not e.get("scraped")]
    if not entries:
        print("[Amazon] All entries already scraped.")
        return

    print(f"[Amazon] Scraping {len(entries)} entries...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        for i, entry in enumerate(entries):
            try:
                page = await context.new_page()
                await page.goto(entry["url"], timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)

                # Title
                title_el = await page.query_selector("#productTitle")
                title = (await title_el.inner_text()).strip() if title_el else ""
                if not title:
                    # fallback: og:title meta
                    meta = await page.query_selector("meta[name='title']")
                    if meta:
                        title = (await meta.get_attribute("content") or "").strip()

                # Price
                price = 0.0
                for sel in [".a-price .a-offscreen", "#priceblock_ourprice",
                             "#priceblock_dealprice", ".a-price-whole"]:
                    el = await page.query_selector(sel)
                    if el:
                        raw = await el.inner_text()
                        cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
                        try:
                            v = float(cleaned)
                            if v > 0:
                                price = v
                                break
                        except ValueError:
                            pass

                # Rating
                rating = 0.0
                rating_el = await page.query_selector(
                    "#acrPopover span.a-icon-alt, [data-hook='rating-out-of-text']"
                )
                if rating_el:
                    m = re.search(r"(\d+\.?\d*)", await rating_el.inner_text())
                    if m:
                        rating = float(m.group(1))

                # Reviews
                review_count = 0
                rev_el = await page.query_selector(
                    "#acrCustomerReviewText, [data-hook='total-review-count']"
                )
                if rev_el:
                    raw = re.sub(r"[^\d]", "", await rev_el.inner_text())
                    review_count = int(raw) if raw else 0

                # Bullets / description
                bullets = await page.query_selector_all(
                    "#feature-bullets li span.a-list-item"
                )
                bullet_texts = []
                for b in bullets:
                    t = (await b.inner_text()).strip()
                    if t:
                        bullet_texts.append(t)
                description = "\n".join(bullet_texts)

                # Images
                main_img_el = await page.query_selector(
                    "#landingImage, #imgBlkFront, #main-image"
                )
                main_image_url = ""
                if main_img_el:
                    main_image_url = (
                        await main_img_el.get_attribute("src") or
                        await main_img_el.get_attribute("data-old-hires") or ""
                    )

                thumb_imgs = await page.query_selector_all("#altImages img")
                image_urls = []
                for img in thumb_imgs:
                    src = await img.get_attribute("src") or ""
                    src = re.sub(r"\._[A-Z0-9_,]+_\.", "._SL500_.", src)
                    if src and "transparent" not in src and src not in image_urls:
                        image_urls.append(src)
                if main_image_url and main_image_url not in image_urls:
                    image_urls.insert(0, main_image_url)

                keywords = _extract_keywords(title + " " + description)

                # Update entry in catalog
                entry.update({
                    "title":          title or entry["asin"],
                    "price":          price,
                    "rating":         rating,
                    "review_count":   review_count,
                    "description":    description,
                    "bullet_count":   len(bullet_texts),
                    "image_count":    len(image_urls),
                    "image_urls":     image_urls,
                    "main_image_url": main_image_url,
                    "keywords":       keywords,
                    "scraped":        True,
                })

                print(f"[Amazon] {i+1}/{len(entries)} ✓ {title[:60] or entry['asin']}")

                await page.close()

                # Save progress every 5 products
                if (i + 1) % 5 == 0:
                    save_catalog(catalog)
                    print(f"  [Saved progress at {i+1}]")

            except Exception as e:
                print(f"[Amazon] {i+1}/{len(entries)} ✗ {entry['asin']}: {e}")
                try:
                    await page.close()
                except Exception:
                    pass

        await browser.close()

    save_catalog(catalog)
    print(f"[Amazon] Done. Catalog saved.")


# ── Blinkit scraper ────────────────────────────────────────────────────────────

async def scrape_blinkit_titles(catalog: dict):
    from playwright.async_api import async_playwright

    entries = [e for e in catalog["blinkit"] if not e.get("scraped")]
    if not entries:
        print("[Blinkit] All entries already scraped.")
        return

    print(f"[Blinkit] Scraping {len(entries)} entries...")

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

        # Hit homepage first for location cookie
        page0 = await context.new_page()
        try:
            await page0.goto("https://blinkit.com", timeout=45000, wait_until="domcontentloaded")
            await page0.wait_for_timeout(2000)
        except Exception:
            pass
        await page0.close()

        for i, entry in enumerate(entries):
            captured = {}

            async def handle_response(response, _captured=captured):
                if "layout" in response.url and ("product" in response.url or "prid" in response.url):
                    try:
                        data = await response.json()
                        snippets = data.get("response", {}).get("snippets", [])
                        for s in snippets:
                            d = s.get("data", {})
                            name = _text(d.get("name"))
                            if name and not _captured.get("title"):
                                _captured.update(d)
                    except Exception:
                        pass

            page = await context.new_page()
            page.on("response", handle_response)

            try:
                await page.goto(entry["url"], timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Try DOM scraping
                title = ""
                for sel in ["h1", "[class*='product-name']", "[class*='ProductName']",
                             "[class*='product_name']"]:
                    el = await page.query_selector(sel)
                    if el:
                        t = (await el.inner_text()).strip()
                        if t and len(t) > 3:
                            title = t
                            break

                price = 0.0
                for sel in ["[class*='Price']", "[class*='price']"]:
                    els = await page.query_selector_all(sel)
                    for el in els:
                        raw = (await el.inner_text()).strip()
                        cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
                        try:
                            v = float(cleaned)
                            if v > 0:
                                price = v
                                break
                        except ValueError:
                            pass
                    if price:
                        break

                image_urls = []
                main_image_url = ""
                for img in await page.query_selector_all("img"):
                    src = await img.get_attribute("src") or ""
                    if src and ("cdn" in src or "blinkit" in src) and src not in image_urls:
                        image_urls.append(src)
                        if not main_image_url:
                            main_image_url = src

                # Fallback from API capture
                if not title and captured:
                    name_field = captured.get("name", {})
                    title = name_field.get("text", "") if isinstance(name_field, dict) else str(name_field)
                    for pk in ("mrp", "normal_price", "price"):
                        raw_field = captured.get(pk, {})
                        raw = raw_field.get("text", "") if isinstance(raw_field, dict) else str(raw_field)
                        cleaned = re.sub(r"[^\d.]", "", raw)
                        try:
                            v = float(cleaned)
                            if v > 0:
                                price = v
                                break
                        except ValueError:
                            pass

                # Final fallback: use slug as title
                if not title:
                    title = entry["slug"].replace("-", " ").title()

                keywords = _extract_keywords(title)

                entry.update({
                    "title":          title,
                    "price":          price,
                    "image_count":    len(image_urls),
                    "image_urls":     image_urls[:8],
                    "main_image_url": main_image_url,
                    "keywords":       keywords,
                    "scraped":        True,
                })

                print(f"[Blinkit] {i+1}/{len(entries)} ✓ {title[:60]}")

            except Exception as e:
                print(f"[Blinkit] {i+1}/{len(entries)} ✗ {entry['product_id']}: {e}")
                entry["title"] = entry["slug"].replace("-", " ").title()
                entry["scraped"] = True

            finally:
                try:
                    await page.close()
                except Exception:
                    pass

            if (i + 1) % 5 == 0:
                save_catalog(catalog)
                print(f"  [Saved progress at {i+1}]")

        await browser.close()

    save_catalog(catalog)
    print("[Blinkit] Done.")


def _text(field) -> str:
    if isinstance(field, dict):
        return str(field.get("text") or "").strip()
    return str(field or "").strip()


def _extract_keywords(text: str) -> list:
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                 "of", "with", "is", "it", "this", "that", "are", "by", "from"}
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:20]]


if __name__ == "__main__":
    catalog = load_catalog()

    amazon_todo  = sum(1 for e in catalog["amazon"]  if not e.get("scraped"))
    blinkit_todo = sum(1 for e in catalog["blinkit"] if not e.get("scraped"))
    print(f"To scrape: {amazon_todo} Amazon + {blinkit_todo} Blinkit")

    asyncio.run(scrape_amazon_titles(catalog))
    asyncio.run(scrape_blinkit_titles(catalog))
    print("All done!")
