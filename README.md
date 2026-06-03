# Lazer Believe — Ranking Tracker

A competitor gap analysis tool that compares your products from [lazerbelieve.com](https://www.lazerbelieve.com) against top results on **Amazon** and **Blinkit** in real time.

---

## What It Does

1. **Auto-discovers all your products** from lazerbelieve.com
2. **Scrapes top 5 competitors** from Amazon and/or Blinkit for any product
3. **Analyzes gaps** across 7 factors: keywords, images, description, bullet points, price, rating, and reviews
4. **Shows a dashboard** with scores, gap table, missing keywords, and priority actions

---

## Project Structure

```
tracker/
├── app.py                        # Flask web server — main entry point
├── analyzer.py                   # Gap scoring and priority action logic
├── requirements.txt              # Python dependencies
├── scrapers/
│   ├── catalog.py                # Discovers all products from lazerbelieve.com
│   ├── amazon.py                 # Scrapes Amazon India search results
│   ├── blinkit.py                # Scrapes Blinkit via API interception
│   └── your_product.py           # Scrapes a single product page (legacy)
└── templates/
    └── dashboard.html            # Web UI
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

### 3. Open in browser

```
http://localhost:5000
```

---

## How to Use

1. Page loads and **automatically scans lazerbelieve.com** — all products appear in the dropdown
2. **Select a product** — the Amazon/Blinkit search keyword is auto-filled
3. **Choose platform** — Amazon, Blinkit, or both
4. Click **Analyze** — wait 30–60 seconds while live data is fetched
5. View the results:

| Section | What it shows |
|---|---|
| Overall Score | 0–10 score vs competitors |
| Score Breakdown | Bar chart per factor |
| Top Competitors | Live results with price, rating, review count |
| Gap Table | Your values vs Top #1 vs Average |
| Missing Keywords | Words competitors use that you don't |
| Priority Actions | Sorted by impact — what to fix first |

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
