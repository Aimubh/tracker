# Code Documentation — Lazer Believe Ranking Tracker

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [APIs & External Services Used](#2-apis--external-services-used)
3. [File-by-File Reference](#3-file-by-file-reference)
   - [app.py — Flask Server & REST API](#apppy--flask-server--rest-api)
   - [analyzer.py — Gap Analysis Engine](#analyzerpy--gap-analysis-engine)
   - [scrapers/catalog.py — Product Discovery](#scraperscatalogpy--product-discovery)
   - [scrapers/amazon.py — Amazon Scraper](#scrapersamazonpy--amazon-scraper)
   - [scrapers/blinkit.py — Blinkit Scraper](#scrapersblinkit py--blinkit-scraper)
4. [Internal REST API Reference](#4-internal-rest-api-reference)
5. [Data Schemas](#5-data-schemas)
6. [Scoring Formula](#6-scoring-formula)
7. [Tech Stack](#7-tech-stack)

---

## 1. Architecture Overview

```
Browser (dashboard.html)
        │
        │  HTTP GET /api/products
        │  HTTP POST /api/analyze
        ▼
   Flask Server (app.py)
        │
        ├──► catalog.py  ──► lazerbelieve.com   (Playwright, headless)
        │
        ├──► amazon.py   ──► amazon.in/s?k=...  (Playwright, headless)
        │                     amazon.in/dp/...   (Playwright, same session)
        │
        ├──► blinkit.py  ──► blinkit.com        (Playwright, visible, off-screen)
        │                     blinkit.com/v1/layout/search  ◄─ API interception
        │
        └──► analyzer.py  (pure Python, no network)
```

**Request flow for one analysis:**
1. Frontend sends `POST /api/analyze` with `product_url`, `keyword`, `platform`
2. `app.py` scrapes your product page via `catalog._scrape_product()`
3. `app.py` calls `scrape_amazon()` and/or `scrape_blinkit()` in sequence
4. All results passed to `analyze()` which returns scores, gaps, and actions
5. JSON response sent back to the dashboard

---

## 2. APIs & External Services Used

### 2.1 Blinkit Internal Search API

| Property | Value |
|---|---|
| **Type** | Undocumented internal REST API (no auth required) |
| **Base URL** | `https://blinkit.com` |
| **Endpoint** | `GET /v1/layout/search` |
| **Triggered by** | Loading `https://blinkit.com/s/?q={keyword}` in a browser |
| **How we access it** | Playwright network interception (`page.on("response", ...)`) |
| **Auth** | None — public endpoint, requires a valid browser session |
| **Location requirement** | Geolocation must be set (we use Mumbai: `19.0760, 72.8777`) |

**Request example (made by the browser automatically):**
```
GET https://blinkit.com/v1/layout/search?q=travel+bottle&search_type=type_to_search
GET https://blinkit.com/v1/layout/search?offset=12&limit=12&actual_query=travel+bottle
```

**Response structure:**
```json
{
  "is_success": true,
  "response": {
    "snippets": [
      {
        "widget_type": "...",
        "data": {
          "name":    { "text": "GUBB Travel Bottle Set", "color": {...}, "font": {...} },
          "variant": { "text": "2 pcs", ... },
          "mrp":     { "text": "₹205", ... },
          "image":   { "url": "https://cdn.grofers.com/..." },
          "click_action": {
            "data": { "slug": "gubb-travel-bottle-set" }
          }
        }
      }
    ],
    "pagination": { "next_offset": 12 }
  }
}
```

**Fields we extract:**

| API Field | Our Field | Notes |
|---|---|---|
| `data.name.text` | `title` | Product name |
| `data.mrp.text` | `price` | Strip `₹` and commas |
| `data.variant.text` | `description` | Weight/quantity like "2 pcs" |
| `data.image.url` | `image_count` | 1 if exists, else 0 |
| `data.click_action.data.slug` | `url` | Used to build `blinkit.com/prn/{slug}` |

---

### 2.2 Amazon India — Web Scraping (No Official API)

| Property | Value |
|---|---|
| **Type** | Web scraping via Playwright (no official public API used) |
| **Search URL** | `https://www.amazon.in/s?k={keyword}` |
| **Product URL** | `https://www.amazon.in/dp/{ASIN}` |
| **Auth** | None — public pages |
| **Anti-bot** | Headless Chromium with spoofed User-Agent |

**We do NOT use:**
- Amazon Product Advertising API (requires seller account + approval)
- Amazon SP-API (requires registered developer)

**DOM selectors used on search page:**

| Selector | Data extracted |
|---|---|
| `[data-component-type='s-search-result']` | Product card container |
| `h2 span.a-text-normal` | Product title |
| `.a-price .a-offscreen` | Price (hidden span with full value) |
| `span.a-icon-alt` | Star rating text e.g. "4.2 out of 5" |
| `span[aria-label*='ratings']` | Review count |
| `.a-badge-label` | Best Seller / Amazon's Choice badge |
| `h2 a` | Link to product detail page |

**DOM selectors used on product detail page:**

| Selector | Data extracted |
|---|---|
| `#feature-bullets li span.a-list-item` | Bullet points / key features |
| `#altImages img` | Alternate product images (image count) |

---

### 2.3 Lazer Believe Website — Web Scraping

| Property | Value |
|---|---|
| **Type** | Web scraping via Playwright |
| **Platform** | Shopify (custom theme named "Minimog") |
| **Homepage** | `https://www.lazerbelieve.com/` |
| **Product pages** | `https://www.lazerbelieve.com/products/{slug}` |
| **Auth** | None — public Shopify store |

**DOM selectors used:**

| Selector | Data extracted | Notes |
|---|---|---|
| `a[href*='/products/']` | All product URLs | Discovered from homepage |
| `h1` | Product title | |
| `.main-product__block-price` | Price container | Scoped to main product, avoids related product prices |
| `re.split("sale price", text)` | Sale price | Splits on label, takes first number after it |
| `.rte` | Full description | Shopify rich text editor block |
| `.m-product-media img` | Product images | Deduplicated by `src` attribute |

---

### 2.4 Playwright (Browser Automation Library)

| Property | Value |
|---|---|
| **Package** | `playwright` (Python) |
| **Browser** | Chromium (installed via `playwright install chromium`) |
| **Modes used** | Headless (Amazon, your site), Visible off-screen (Blinkit) |
| **Version** | 1.60.0 |

**Why visible for Blinkit:**
Blinkit detects `navigator.webdriver = true` in headless mode and stalls the page load. Running with `headless=False` + `--window-position=-32000,-32000` (off-screen) + injecting `navigator.webdriver = undefined` bypasses this.

---

## 3. File-by-File Reference

---

### `app.py` — Flask Server & REST API

**Purpose:** Entry point. Serves the dashboard HTML and exposes two REST endpoints.

```
app.py
├── GET  /                → serves dashboard.html
├── GET  /api/products    → scans lazerbelieve.com, returns product list
└── POST /api/analyze     → scrapes your product + competitors, returns analysis
```

#### Functions

```python
index() → renders templates/dashboard.html
```

```python
api_products()
  Calls:  get_all_products()           # from catalog.py
  Returns: list of product summaries
  Fields:  title, url, price, category, amazon_keyword, image_count, description_word_count
```

```python
api_analyze()
  Input JSON:  { product_url, keyword, platform }
  platform:    "amazon" | "blinkit" | "both"

  Calls (in order):
    1. _scrape_product(context, product_url)   # catalog.py
    2. scrape_amazon(keyword, max_results=5)   # if platform == amazon|both
    3. scrape_blinkit(keyword, max_results=5)  # if platform == blinkit|both
    4. analyze(your_product, competitors)      # analyzer.py

  Returns: full analysis dict (see Data Schemas section)
```

---

### `analyzer.py` — Gap Analysis Engine

**Purpose:** Pure Python. Takes your product dict and a list of competitor dicts. Returns scores, gaps, missing keywords, and a priority action list. No network calls.

#### Public function

```python
analyze(your_product: dict, competitors: list[dict]) -> dict
```

#### Internal scoring functions (all return float 0.0–10.0)

| Function | What it measures |
|---|---|
| `_score_keywords(yours, comps)` | Keyword overlap: `len(your_kw ∩ all_comp_kw) / len(all_comp_kw) × 10` |
| `_score_images(yours, avg)` | `(your_image_count / avg_image_count) × 10` |
| `_score_description(yours, avg)` | `(your_word_count / avg_word_count) × 10` |
| `_score_price(yours, comps)` | % of competitors you are cheaper than × 10 |
| `_score_rating(yours, avg)` | `(your_rating / avg_rating) × 10` |
| `_score_reviews(yours, avg)` | `log1p(your_reviews) / log1p(avg_reviews) × 10` (log scale to avoid outlier bias) |
| `_score_bullets(yours, avg)` | `(your_bullets / avg_bullets) × 10` |

#### Gap computation

`_compute_gaps(yours, top, avg)` — for each of 7 fields, computes:
- `yours` — your raw value
- `top` — top #1 competitor's value
- `avg` — average across all competitors
- `diff` — `yours - avg` (negative = behind)
- `status` — `"good"` or `"behind"` (price: lower = good; all others: higher = good)

#### Priority actions

`_priority_actions(gaps, scores)` — sorted by score ascending (worst first). Any factor scoring below **7.0** generates an action item with `impact: "high"` or `"medium"`.

---

### `scrapers/catalog.py` — Product Discovery

**Purpose:** Discovers all product URLs from the homepage and scrapes each product page.

#### Functions

```python
get_all_products() -> list[dict]
  1. Opens lazerbelieve.com homepage
  2. Finds all <a href="/products/..."> links
  3. Deduplicates by URL
  4. Calls _scrape_product() for each URL
  Returns: list of product dicts
```

```python
_scrape_product(context, url: str) -> dict | None
  Scrapes a single product page.
  Extracts: title, price, description, image_count, bullet_count, keywords, amazon_keyword
  Price: uses _extract_price() scoped to .main-product__block-price
  Description: .rte element (Shopify rich text block)
  Images: .m-product-media img, deduplicated by src
```

```python
_make_search_keyword(title: str) -> str
  Removes brand name "lazer" and filler words from the title.
  Returns top 5 meaningful words as the Amazon/Blinkit search keyword.
  Example: "Lazer Pure Borosilicate Glass Water Bottle 750ml"
        →  "borosilicate glass water bottle 750ml"
```

---

### `scrapers/amazon.py` — Amazon Scraper

**Purpose:** Scrapes top N Amazon India search results for a keyword using a single Playwright browser session.

#### Functions

```python
scrape_amazon(keyword: str, max_results: int = 5) -> list[dict]
  Entry point. Launches browser, calls _run(), closes browser.
```

```python
_run(browser, keyword, max_results) -> list[dict]
  1. Opens amazon.in/s?k={keyword}
  2. Finds all [data-component-type='s-search-result'] cards
  3. Calls _extract_card_data() for each card while page is open
  4. Closes the search page
  5. Calls _scrape_product_page() for each card's URL (new tab, same context)
  6. Closes the browser context

  NOTE: Card element handles are tied to the page — must extract all card data
  BEFORE closing the search page, then fetch product pages after.
```

```python
_extract_card_data(card) -> dict | None
  Extracts from a search result card:
  title, price, rating, review_count, badges, url
  Filters out cards where title == "Sponsored"
```

```python
_scrape_product_page(context, url) -> dict
  Opens product page in a new browser tab (same context, no nested playwright).
  Extracts: bullet points (#feature-bullets), image count (#altImages)
  Always closes the tab in a finally block.
```

---

### `scrapers/blinkit.py` — Blinkit Scraper

**Purpose:** Intercepts Blinkit's internal `v1/layout/search` API calls using Playwright's response listener. Does NOT do DOM scraping.

#### Why API interception instead of DOM scraping

Blinkit is a React SPA with deferred JS bundles. The HTML returned at load time is an empty shell — all product data is injected by JavaScript after the bundles execute. Additionally, Blinkit detects `headless=True` and hangs the page load entirely. DOM scraping returns zero results.

#### Functions

```python
scrape_blinkit(keyword: str, max_results: int = 5) -> list[dict]
  1. Launches Chromium with headless=False, window moved off-screen
  2. Injects: navigator.webdriver = undefined  (masks automation)
  3. Sets geolocation: Mumbai (19.0760, 72.8777) — required for listings
  4. Registers page.on("response", handle_response) listener
  5. Navigates to blinkit.com (homepage) → then /s/?q={keyword}
  6. Waits 5s for API calls to fire and be captured
  7. Calls _parse_snippets() on captured data
  8. Closes browser
```

```python
handle_response(response)  [inner async function]
  Fires on every network response.
  Filters for URLs containing "layout/search".
  Parses response JSON and appends snippets to captured list.
```

```python
_parse_snippets(snippets, max_results) -> list[dict]
  Iterates over Blinkit API snippets.
  Calls _text() to unwrap nested field objects.
  Extracts: name, price (from mrp/normal_price), variant, image, slug.
```

```python
_text(field) -> str
  Blinkit API fields are objects: {"text": "...", "color": {...}, "font": {...}}
  This helper extracts just the .text value safely.
```

---

## 4. Internal REST API Reference

### `GET /api/products`

Scans lazerbelieve.com live and returns all discovered products.

**Response `200`:**
```json
[
  {
    "title": "Lazer Travel Bottle Set",
    "url": "https://www.lazerbelieve.com/products/lazer-travel-bottle-set",
    "price": 299.0,
    "category": "Travel Bottle Set",
    "amazon_keyword": "travel bottle set",
    "image_count": 8,
    "description_word_count": 145
  }
]
```

**Response `500`:**
```json
{ "error": "error message" }
```

---

### `POST /api/analyze`

Scrapes your product + competitors and returns gap analysis.

**Request body:**
```json
{
  "product_url": "https://www.lazerbelieve.com/products/lazer-travel-bottle-set",
  "keyword": "travel bottle set",
  "platform": "amazon"
}
```

| Field | Type | Required | Values |
|---|---|---|---|
| `product_url` | string | Yes | Any lazerbelieve.com product URL |
| `keyword` | string | Yes | Search keyword for Amazon/Blinkit |
| `platform` | string | No | `"amazon"` (default) \| `"blinkit"` \| `"both"` |

**Response `200`:**
```json
{
  "overall_score": 4.2,
  "search_keyword": "travel bottle set",
  "platform": "amazon",
  "warnings": [],
  "competitors_count": 5,
  "scores": {
    "title_keywords": 3.5,
    "image_count": 8.0,
    "description": 6.2,
    "price": 5.0,
    "rating": 0.0,
    "reviews": 0.0,
    "bullet_points": 4.1
  },
  "gaps": [
    {
      "label": "Price (₹)",
      "yours": 299.0,
      "top": 199.0,
      "avg": 245.0,
      "diff": 54.0,
      "status": "behind",
      "category": "pricing"
    }
  ],
  "missing_keywords": ["leak", "proof", "bpa", "free"],
  "priority_actions": [
    {
      "title": "Build up review count",
      "detail": "Competitors have more reviews which boosts ranking...",
      "impact": "high",
      "score": 0.0,
      "key": "reviews"
    }
  ],
  "your_product": { ... },
  "top_competitor": { ... },
  "competitors": [ ... ]
}
```

**Response `400`:** Missing/invalid input or no competitor results found

**Response `500`:** Scraping or server error (includes `trace` field for debugging)

---

## 5. Data Schemas

### Product dict (your product or competitor)

```python
{
  "source":               str,    # "lazerbelieve.com" | "amazon" | "blinkit"
  "platform":             str,    # "website" | "amazon" | "blinkit"
  "title":                str,
  "url":                  str,
  "price":                float,  # in INR
  "description":          str,    # full text or bullet points joined
  "description_word_count": int,
  "image_count":          int,
  "bullet_count":         int,
  "rating":               float | None,   # 0.0–5.0, None if no rating
  "review_count":         int,
  "keywords":             list[str],      # top 20 extracted keywords
  "has_best_seller_badge": bool,
  "has_choice_badge":     bool,           # Amazon's Choice (Amazon only)
  "category":             str,            # your product only
  "amazon_keyword":       str,            # your product only
}
```

### Gap dict

```python
{
  "label":    str,    # e.g. "Price (₹)"
  "yours":    float,
  "top":      float,  # top #1 competitor
  "avg":      float,  # average across all competitors
  "diff":     float,  # yours - avg
  "status":   str,    # "good" | "behind"
  "category": str,    # "keywords" | "images" | "content" | "trust" | "pricing"
}
```

### Action dict

```python
{
  "title":   str,   # short action name
  "detail":  str,   # explanation
  "impact":  str,   # "high" | "medium"
  "score":   float, # the score that triggered this action
  "key":     str,   # the score key e.g. "reviews"
}
```

---

## 6. Scoring Formula

All scores are on a **0–10 scale**. Overall score = average of all 7.

```
title_keywords  = (|your_keywords ∩ competitor_keywords| / |all_competitor_keywords|) × 10
image_count     = min((your_images / avg_images) × 10, 10)
description     = min((your_words / avg_words) × 10, 10)
price           = (count of competitors where your_price ≤ their_price / total_competitors) × 10
rating          = min((your_rating / avg_rating) × 10, 10)
reviews         = min((log(1 + your_reviews) / log(1 + avg_reviews)) × 10, 10)
bullet_points   = min((your_bullets / avg_bullets) × 10, 10)
```

**Why log scale for reviews?**
Review counts vary from 0 to 100,000+. A linear scale would make a product with 0 reviews score 0 even against a competitor with only 50 reviews. `log1p` compresses the scale so the gap feels proportional.

**Why price score is different?**
Price is the only factor where lower = better. We count how many competitors you're cheaper than, then convert to a 0–10 score. If you're cheaper than all 5, score = 10. Cheaper than none, score = 0.

---

## 7. Tech Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Web framework | Flask | 3.1.3 | REST API + HTML serving |
| Browser automation | Playwright (Python) | 1.60.0 | Scraping Amazon, Blinkit, your site |
| Browser engine | Chromium | 148.x | Rendered by Playwright |
| HTML parsing | BeautifulSoup4 | 4.14.3 | Fallback HTML parsing |
| HTTP | requests | 2.32.3 | Lightweight HTTP calls |
| Frontend | Vanilla HTML/CSS/JS | — | No framework, single file |
| Runtime | Python | 3.12 | |
| OS tested | Windows 11 | — | |

---

*Generated for internal use — Lazer Believe Ranking Tracker MVP*
