"""
Flask app — Lazer Believe Ranking Tracker
Run: python app.py  →  open http://localhost:5000
"""

import asyncio
from flask import Flask, render_template, request, jsonify

from scrapers.catalog import get_all_products
from scrapers.amazon import scrape_amazon
from analyzer import analyze

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/products", methods=["GET"])
def api_products():
    """Scrape lazerbelieve.com live and return all products."""
    try:
        products = asyncio.run(get_all_products())
        return jsonify([
            {
                "title": p["title"],
                "url": p["url"],
                "price": p["price"],
                "category": p["category"],
                "amazon_keyword": p["amazon_keyword"],
                "image_count": p["image_count"],
                "description_word_count": p["description_word_count"],
            }
            for p in products
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Accepts a product URL from lazerbelieve.com + optional keyword override,
    scrapes it live, then scrapes Amazon for top competitors, and returns gap analysis.
    """
    data = request.get_json()
    product_url = data.get("product_url", "").strip()
    keyword = data.get("keyword", "").strip()
    platform = data.get("platform", "amazon")  # amazon | blinkit | both

    if not product_url:
        return jsonify({"error": "product_url is required"}), 400

    try:
        # Scrape your product live
        from scrapers.catalog import _scrape_product
        from scrapers.blinkit import scrape_blinkit
        from playwright.async_api import async_playwright

        async def scrape_your():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                your_product = await _scrape_product(context, product_url)
                await browser.close()
            return your_product

        your_product = asyncio.run(scrape_your())

        if not your_product:
            return jsonify({"error": "Could not scrape your product page."}), 400

        search_keyword = keyword or your_product.get("amazon_keyword", "")
        if not search_keyword:
            return jsonify({"error": "Could not determine search keyword."}), 400

        # Scrape competitors from selected platform(s)
        competitors = []
        warnings = []

        if platform in ("amazon", "both"):
            amazon_results = asyncio.run(scrape_amazon(search_keyword, max_results=5))
            if amazon_results:
                competitors.extend(amazon_results)
            else:
                warnings.append(f"Amazon returned no results for '{search_keyword}'.")

        if platform in ("blinkit", "both"):
            blinkit_results = asyncio.run(scrape_blinkit(search_keyword, max_results=5))
            if blinkit_results:
                competitors.extend(blinkit_results)
            else:
                warnings.append(f"Blinkit returned no results for '{search_keyword}' (may be slow/blocked).")

        if not competitors:
            return jsonify({"error": f"No results found on {platform} for '{search_keyword}'. Try a different keyword.", "warnings": warnings}), 400

        result = analyze(your_product, competitors)
        result["warnings"] = warnings
        result["search_keyword"] = search_keyword
        result["platform"] = platform
        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


if __name__ == "__main__":
    print("Starting Lazer Believe Ranking Tracker...")
    print("Open http://localhost:5000")
    app.run(debug=False, port=5000)
