"""
Discovers all products from lazerbelieve.com using THREE complementary sources
so no product is ever missed — including newly added ones:

  1. sitemap_products_1.xml  — Shopify maintains this in real time (most complete)
  2. /collections/all/products.json  — Shopify public API (has price + images)
  3. /sitemap.xml  — finds any extra product sitemap files (if >1 page of products)

The sitemap gives us all URLs. The JSON API enriches them with price/images.
Both are merged by handle so there's no duplication.
"""

import asyncio
import re
import requests
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

BASE_URL       = "https://www.lazerbelieve.com"
SITEMAP_INDEX  = f"{BASE_URL}/sitemap.xml"
PRODUCTS_API   = f"{BASE_URL}/collections/all/products.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_all_product_urls() -> list[dict]:
    """
    Merges products from the sitemap + Shopify JSON API.
    Returns a deduplicated, enriched list sorted by title.
    """
    # Step 1 — get all product URLs from sitemap (most complete, real-time)
    sitemap_urls = _fetch_sitemap_urls()
    print(f"[Catalog] Sitemap: {len(sitemap_urls)} product URLs")

    # Step 2 — get enriched product data from Shopify JSON API
    api_products = _fetch_api_products()
    print(f"[Catalog] API: {len(api_products)} products with full data")

    # Step 3 — build a lookup by handle from the API
    api_by_handle = {p["handle"]: p for p in api_products}

    # Step 4 — merge: start with sitemap URLs, enrich with API data where available
    merged = {}
    for url in sitemap_urls:
        handle = url.rstrip("/").split("/products/")[-1]
        if handle in api_by_handle:
            # Full data from API
            merged[handle] = api_by_handle[handle]
        else:
            # Sitemap-only product — create a basic entry
            # (product exists on site but not yet in the public JSON API)
            title = _handle_to_title(handle)
            merged[handle] = {
                "title": title,
                "handle": handle,
                "url": url,
                "price": 0.0,
                "image_count": 0,
                "description": "",
                "description_word_count": 0,
                "category": _extract_category(handle),
                "amazon_keyword": _make_search_keyword(title),
                "keywords": _extract_keywords(title),
                "bullet_count": 0,
                "rating": None,
                "review_count": 0,
                "has_best_seller_badge": False,
                "platform": "website",
                "source": "lazerbelieve.com",
            }

    # Also include any API products not in the sitemap
    for handle, product in api_by_handle.items():
        if handle not in merged:
            merged[handle] = product

    products = sorted(merged.values(), key=lambda p: p["title"].lower())
    print(f"[Catalog] Total after merge: {len(products)} unique products")
    return products


# ── Source 1: Sitemap ─────────────────────────────────────────────────────────

def _fetch_sitemap_urls() -> list[str]:
    """Parses sitemap.xml to find all product sitemap files, then extracts every product URL."""
    product_urls = []
    try:
        # Get the sitemap index
        resp = requests.get(SITEMAP_INDEX, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Find all product sitemap URLs (may be multiple pages)
        product_sitemaps = []
        for sitemap in root.findall("sm:sitemap", ns):
            loc = sitemap.findtext("sm:loc", namespaces=ns) or ""
            if "sitemap_products" in loc:
                product_sitemaps.append(loc)

        print(f"[Catalog] Found {len(product_sitemaps)} product sitemap file(s)")

        # Parse each product sitemap file
        for sitemap_url in product_sitemaps:
            try:
                resp2 = requests.get(sitemap_url, headers=HEADERS, timeout=10)
                resp2.raise_for_status()
                root2 = ET.fromstring(resp2.content)
                for url_el in root2.findall("sm:url", ns):
                    loc = url_el.findtext("sm:loc", namespaces=ns) or ""
                    if "/products/" in loc and loc not in product_urls:
                        product_urls.append(loc)
            except Exception as e:
                print(f"[Catalog] Sitemap parse error ({sitemap_url}): {e}")

    except Exception as e:
        print(f"[Catalog] Sitemap index error: {e}")

    return product_urls


# ── Source 2: Shopify JSON API ────────────────────────────────────────────────

def _fetch_api_products() -> list[dict]:
    """Fetches enriched product data (price, images, description) from Shopify API."""
    all_products = []
    page = 1

    while True:
        try:
            resp = requests.get(
                PRODUCTS_API,
                params={"limit": 250, "page": page},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            products = resp.json().get("products", [])

            if not products:
                break

            for p in products:
                handle = p.get("handle", "")
                title = p.get("title", "").strip()
                if not handle or not title:
                    continue

                # Lowest variant price
                price = 0.0
                for v in p.get("variants", []):
                    try:
                        price = float(v.get("price", 0))
                        if price > 0:
                            break
                    except (ValueError, TypeError):
                        pass

                # Strip HTML from description
                description = re.sub(r"<[^>]+>", " ", p.get("body_html", "") or "")
                description = re.sub(r"\s+", " ", description).strip()

                all_products.append({
                    "title": title,
                    "handle": handle,
                    "url": f"{BASE_URL}/products/{handle}",
                    "price": price,
                    "image_count": len(p.get("images", [])),
                    "description": description,
                    "description_word_count": len(description.split()),
                    "category": _extract_category(handle),
                    "amazon_keyword": _make_search_keyword(title),
                    "keywords": _extract_keywords(title + " " + description),
                    "bullet_count": description.count("."),
                    "rating": None,
                    "review_count": 0,
                    "has_best_seller_badge": False,
                    "platform": "website",
                    "source": "lazerbelieve.com",
                })

            if len(products) < 250:
                break
            page += 1

        except Exception as e:
            print(f"[Catalog] API error on page {page}: {e}")
            break

    return all_products


# ── Individual product page scraper (used during analysis) ───────────────────

async def get_all_products() -> list[dict]:
    """Async wrapper — kept for compatibility."""
    return fetch_all_product_urls()


async def _scrape_product(context, url: str) -> dict | None:
    """Scrapes a single product page for live price, description, and images."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        title_el = await page.query_selector("h1")
        title = (await title_el.inner_text()).strip() if title_el else ""
        if not title:
            return None

        price = await _extract_price(page)

        desc_el = await page.query_selector(".rte")
        description = (await desc_el.inner_text()).strip() if desc_el else ""

        imgs = await page.query_selector_all(".m-product-media img, [class*='product-media'] img")
        seen_src = set()
        image_count = 0
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if src and src not in seen_src:
                seen_src.add(src)
                image_count += 1

        bullet_count = len([l for l in description.splitlines() if l.strip() and len(l.strip()) < 100])
        keywords = _extract_keywords(title + " " + description)

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
        "category": _extract_category(url),
        "amazon_keyword": _make_search_keyword(title),
        "has_best_seller_badge": False,
        "platform": "website",
        "source": "lazerbelieve.com",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _handle_to_title(handle: str) -> str:
    """Convert a URL handle to a readable title."""
    words = handle.replace("-", " ").split()
    # Capitalize and remove leading 'lazer'
    if words and words[0].lower() == "lazer":
        words = ["Lazer"] + [w.capitalize() for w in words[1:]]
    else:
        words = [w.capitalize() for w in words]
    return " ".join(words[:10])  # cap at 10 words


def _extract_category(url_or_handle: str) -> str:
    slug = url_or_handle.rstrip("/").split("/products/")[-1]
    words = slug.replace("-", " ").split()
    if words and words[0].lower() == "lazer":
        words = words[1:]
    return " ".join(words[:4]).title()


def _make_search_keyword(title: str) -> str:
    stopwords = {"lazer", "pure", "mini", "new", "the", "a", "an", "and", "in", "for",
                 "with", "of", "1", "set", "ml", "inch", "kit", "pcs", "pack", "cm"}
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
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    products = fetch_all_product_urls()
    print(f"\nTotal: {len(products)}")
    for p in products:
        print(f"  {p['title']} | ₹{p['price']} | kw: {p['amazon_keyword']}")
