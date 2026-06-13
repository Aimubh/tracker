# Lazer Believe — Ranking Tracker

A competitor gap analysis tool that compares your **Amazon** and **Blinkit** listings against the top results in their category, in real time — and tells you exactly what to fix to rank #1.

---

## What It Does

1. **Loads your listings** from per-platform catalogs (`amazon_catalog.json`, `blinkit_catalog.json`), built from `Active Listings Links.xlsx`
2. **Scrapes top 5 competitors** from Amazon and/or Blinkit for any product, then **filters out off-category results and your own brand** so the comparison is apples-to-apples
3. **Analyzes gaps** across 7 factors: keywords, images, description, bullet points, price, rating, and reviews
4. **Shows a dashboard** with scores, gap table, missing keywords, side-by-side image comparison, and a **🎯 Roadmap to #1** — concrete, ranked steps vs the actual #1 competitor
5. **(Optional) AI rewrite** — with a Claude API key, rewrites your title, bullets, and backend keywords to outrank competitors
6. **Add new products on the fly** — paste any Amazon/Blinkit URL on the dashboard; it's scraped live and added to your catalog, ready to analyze

---

## Project Structure

```
tracker/
├── app.py                        # Flask web server — main entry point
├── analyzer.py                   # Gap scoring, priority actions, Roadmap to #1
├── requirements.txt              # Python dependencies
├── amazon_catalog.json           # Your Amazon listings (built from Excel, enriched by scraper)
├── blinkit_catalog.json          # Your Blinkit listings
├── build_catalog.py              # One-time: Excel → catalog JSON (placeholders)
├── scrape_catalog.py             # Enriches catalogs with live title/price/images (resumable)
├── scrapers/
│   ├── amazon.py                 # Scrapes Amazon India search + own listings
│   └── blinkit.py                # Scrapes Blinkit via internal-API interception
└── templates/
    └── dashboard.html            # Web UI (dropdown, add-product, results, roadmap, AI)
```

---

## Setup

### 1. Install dependencies

```bash
cd tracker
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the server

```bash
python app.py
```

### 3. (Optional) Build / refresh the catalog

```bash
python build_catalog.py     # Excel → catalog JSON (run once after updating the Excel)
python scrape_catalog.py    # Enrich with live title/price/images (resumable; skips done)
```

### 4. (Optional) Enable AI rewrite

```bash
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...     # Windows (PowerShell: $env:ANTHROPIC_API_KEY="...")
```
Without a key, everything works except the "✨ AI: Rewrite my listing" button, which shows a prompt to set the key.

### 5. Open in browser

```
http://localhost:5000
```

---

## How to Use

1. **Pick a platform tab** (Amazon / Blinkit) and **select a product** from the searchable dropdown — or click **+ Add new product** to paste a fresh URL (it's scraped and added live).
2. Click **Analyze** — wait ~30–90 seconds while your listing and the top competitors are fetched.
3. View the results:

| Section | What it shows |
|---|---|
| Overall Score | 0–10 score vs competitors |
| 🎯 Roadmap to #1 | Ranked, concrete steps vs the actual #1 competitor (exact targets) |
| Score Breakdown | Bar chart per factor |
| Top Competitors | Live results (off-category + own-brand results filtered out) |
| Image Comparison | Your images side-by-side with the top competitor |
| Gap Table | Your values vs Top #1 vs Average |
| Missing Keywords | Words competitors use that you don't |
| Priority Actions | Sorted by impact — what to fix first |
| ✨ AI Rewrite | (with API key) Claude-rewritten title, bullets, and backend keywords |

---

## How Each Scraper Works

### Amazon (`scrapers/amazon.py`)
- Uses **Playwright** (headless Chromium) to load Amazon India search results
- Extracts product cards using `[data-component-type='s-search-result']`
- Opens each product page in a new tab (same browser session) to get bullet points and image count
- Filters out "Sponsored" cards

### Blinkit (`scrapers/blinkit.py`)
- Blinkit blocks headless Chrome, so we run with a **hidden visible browser** (`headless=False`, moved off-screen)
- Injects a script to mask the `navigator.webdriver` flag
- Sets geolocation to Mumbai so Blinkit unlocks product listings
- **Intercepts the `v1/layout/search` API response** (Blinkit's internal search API) instead of DOM scraping — the API returns product names, prices, and images as JSON
- Parses nested field format: `{"text": "...", "color": {...}}` used throughout the API

### Your Product (`scrapers/catalog.py`)
- Discovers all product URLs from the homepage (`/products/` links)
- Scrapes each product page for title, price (scoped to `.main-product__block-price`), description (`.rte`), and images (`.m-product-media img`)
- Auto-generates an Amazon search keyword from the product title (removes brand name and filler words)

### Gap Analyzer (`analyzer.py`)
Scores your product vs competitor average on a 0–10 scale:

| Factor | Scoring logic |
|---|---|
| Title keywords | Overlap between your keywords and all competitor keywords |
| Image count | Your count / competitor average |
| Description | Your word count / competitor average |
| Price | % of competitors you are cheaper than |
| Rating | Your rating / competitor average |
| Reviews | log(your reviews) / log(avg reviews) |
| Bullet points | Your bullet count / competitor average |

---

## Known Limitations

- **Amazon** may occasionally return 0 results if the search keyword is too specific — try a broader keyword
- **Blinkit** requires a real browser window (runs off-screen) — slower than headless
- Your product has no reviews or ratings since it's scraped from your website, not a marketplace
- Image count for your product reflects images on your website, not your Amazon listing

---

## Dependencies

| Package | Purpose |
|---|---|
| `flask` | Web server |
| `playwright` | Browser automation (Amazon + Blinkit) |
| `beautifulsoup4` | HTML parsing (fallback) |
| `requests` | HTTP requests |
| `lxml` | HTML parser |
| `python-dotenv` | Environment variables |

---

## Built By

Built as an MVP for **Lazer Believe** to understand why competitor products rank higher on Amazon and Blinkit, and what specific gaps to fix.
