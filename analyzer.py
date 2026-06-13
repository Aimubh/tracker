"""
Gap analyzer — compares your product against top competitors.
Produces scores, gaps, and a prioritized action list.
Supports our_amazon_data / our_blinkit_data for direct listing comparison.
"""


def analyze(your_product: dict, competitors: list[dict],
            our_amazon_data: dict = None, our_blinkit_data: dict = None) -> dict:
    if not competitors:
        return {"error": "No competitor data available"}

    # If we have our own listing data, use that for scoring instead of Shopify data
    amazon_comps = [c for c in competitors if c.get("platform") == "amazon"]
    blinkit_comps = [c for c in competitors if c.get("platform") == "blinkit"]

    # Use amazon data as primary if available, otherwise shopify
    your_primary = our_amazon_data or our_blinkit_data or your_product

    top = competitors[0]
    avg = _average(competitors)

    scores = {
        "title_keywords":  _score_keywords(your_primary, competitors),
        "image_count":     _score_images(your_primary, avg),
        "description":     _score_description(your_primary, avg),
        "price":           _score_price(your_primary, competitors),
        "rating":          _score_rating(your_primary, avg),
        "reviews":         _score_reviews(your_primary, avg),
        "bullet_points":   _score_bullets(your_primary, avg),
    }

    gaps = _compute_gaps(your_primary, top, avg)
    missing_keywords = _missing_keywords(your_primary, competitors)
    actions = _priority_actions(scores)
    roadmap = _roadmap_to_top(your_primary, top, missing_keywords)

    # Image comparison data
    image_comparison = _build_image_comparison(
        our_amazon_data, our_blinkit_data,
        amazon_comps, blinkit_comps
    )

    return {
        "your_product": your_product,
        "our_amazon_data": our_amazon_data,
        "our_blinkit_data": our_blinkit_data,
        "top_competitor": top,
        "avg_competitor": avg,
        "competitors": competitors,
        "competitors_count": len(competitors),
        "scores": scores,
        "gaps": gaps,
        "missing_keywords": missing_keywords,
        "priority_actions": actions,
        "overall_score": round(sum(scores.values()) / len(scores), 1),
        "image_comparison": image_comparison,
        "roadmap": roadmap,
    }


def _build_image_comparison(our_amazon, our_blinkit, amazon_comps, blinkit_comps):
    """Build side-by-side image comparison data for the dashboard."""
    result = {}

    # Amazon image comparison
    if our_amazon and our_amazon.get("image_urls"):
        top_amazon = amazon_comps[0] if amazon_comps else None
        result["amazon"] = {
            "ours": {
                "title": our_amazon.get("title", "Our Product"),
                "images": our_amazon.get("image_urls", [])[:8],
                "count": our_amazon.get("image_count", 0),
                "url": our_amazon.get("url", ""),
            },
            "competitor": {
                "title": top_amazon.get("title", "") if top_amazon else "",
                "images": top_amazon.get("image_urls", []) if top_amazon else [],
                "count": top_amazon.get("image_count", 0) if top_amazon else 0,
                "url": top_amazon.get("url", "") if top_amazon else "",
            } if top_amazon else None,
            "verdict": _image_verdict(
                our_amazon.get("image_count", 0),
                top_amazon.get("image_count", 0) if top_amazon else 0,
            ),
        }

    # Blinkit image comparison
    if our_blinkit and our_blinkit.get("image_urls"):
        top_blinkit = blinkit_comps[0] if blinkit_comps else None
        result["blinkit"] = {
            "ours": {
                "title": our_blinkit.get("title", "Our Product"),
                "images": our_blinkit.get("image_urls", [])[:8],
                "count": our_blinkit.get("image_count", 0),
                "url": our_blinkit.get("url", ""),
            },
            "competitor": {
                "title": top_blinkit.get("title", "") if top_blinkit else "",
                "images": [],
                "count": top_blinkit.get("image_count", 0) if top_blinkit else 0,
                "url": top_blinkit.get("url", "") if top_blinkit else "",
            } if top_blinkit else None,
            "verdict": _image_verdict(
                our_blinkit.get("image_count", 0),
                top_blinkit.get("image_count", 0) if top_blinkit else 0,
            ),
        }

    return result


def _image_verdict(ours: int, theirs: int) -> dict:
    diff = ours - theirs
    if diff >= 0:
        return {"status": "good", "message": f"You have {ours} images — on par or better than top competitor ({theirs})"}
    else:
        return {"status": "behind", "message": f"You have {ours} images vs competitor's {theirs} — add {abs(diff)} more"}


# ── Scoring helpers (0–10 scale) ──────────────────────────────────────────────

def _score_keywords(yours: dict, comps: list[dict]) -> float:
    your_kw = set(yours.get("keywords", []))
    all_comp_kw = set(k for c in comps for k in c.get("keywords", []))
    if not all_comp_kw:
        return 5.0
    overlap = len(your_kw & all_comp_kw) / len(all_comp_kw)
    return round(min(overlap * 10, 10), 1)


def _score_images(yours: dict, avg: dict) -> float:
    your_count = yours.get("image_count", 0)
    avg_count = avg.get("image_count", 1)
    if avg_count == 0:
        return 10.0
    return round(min((your_count / avg_count) * 10, 10), 1)


def _score_description(yours: dict, avg: dict) -> float:
    your_wc = yours.get("description_word_count", 0)
    avg_wc = avg.get("description_word_count", 1)
    if avg_wc == 0:
        return 10.0
    return round(min((your_wc / avg_wc) * 10, 10), 1)


def _score_price(yours: dict, comps: list[dict]) -> float:
    your_price = yours.get("price", 0)
    prices = [c.get("price", 0) for c in comps if c.get("price", 0) > 0]
    if not prices or your_price == 0:
        return 5.0
    cheaper_count = sum(1 for p in prices if your_price <= p)
    return round((cheaper_count / len(prices)) * 10, 1)


def _score_rating(yours: dict, avg: dict) -> float:
    your_r = yours.get("rating") or 0
    avg_r = avg.get("rating") or 0
    if avg_r == 0:
        return 5.0
    return round(min((your_r / avg_r) * 10, 10), 1)


def _score_reviews(yours: dict, avg: dict) -> float:
    your_rc = yours.get("review_count", 0)
    avg_rc = avg.get("review_count", 1)
    if avg_rc == 0:
        return 10.0
    import math
    your_log = math.log1p(your_rc)
    avg_log = math.log1p(avg_rc)
    return round(min((your_log / avg_log) * 10, 10), 1) if avg_log > 0 else 5.0


def _score_bullets(yours: dict, avg: dict) -> float:
    your_b = yours.get("bullet_count", 0)
    avg_b = avg.get("bullet_count", 1)
    if avg_b == 0:
        return 10.0
    return round(min((your_b / avg_b) * 10, 10), 1)


# ── Gap computation ────────────────────────────────────────────────────────────

def _compute_gaps(yours: dict, top: dict, avg: dict) -> list[dict]:
    fields = [
        ("Title keyword count",  "keywords",              len, "keywords"),
        ("Image count",          "image_count",           None, "images"),
        ("Description words",    "description_word_count",None, "content"),
        ("Bullet points",        "bullet_count",          None, "content"),
        ("Rating",               "rating",                None, "trust"),
        ("Review count",         "review_count",          None, "trust"),
        ("Price (₹)",            "price",                 None, "pricing"),
    ]

    gaps = []
    for label, key, transform, category in fields:
        your_val = yours.get(key, 0) or 0
        top_val  = top.get(key, 0) or 0
        avg_val  = avg.get(key, 0) or 0

        if transform:
            your_val = transform(your_val)
            top_val  = transform(top_val)
            avg_val  = transform(avg_val)

        your_val = round(your_val, 1)
        top_val  = round(top_val, 1)
        avg_val  = round(avg_val, 1)

        if key == "price":
            diff = your_val - avg_val
            status = "good" if diff <= 0 else "behind"
        else:
            diff = your_val - avg_val
            status = "good" if diff >= 0 else "behind"

        gaps.append({
            "label":    label,
            "yours":    your_val,
            "top":      top_val,
            "avg":      avg_val,
            "diff":     round(diff, 1),
            "status":   status,
            "category": category,
        })

    return gaps


def _missing_keywords(yours: dict, comps: list[dict]) -> list[str]:
    your_kw = set(yours.get("keywords", []))
    comp_kw_freq: dict[str, int] = {}
    for c in comps:
        for k in c.get("keywords", []):
            comp_kw_freq[k] = comp_kw_freq.get(k, 0) + 1

    missing = [k for k, freq in comp_kw_freq.items()
               if freq >= 2 and k not in your_kw]
    return sorted(missing, key=lambda k: -comp_kw_freq[k])[:15]


def _priority_actions(scores: dict) -> list[dict]:
    actions = []

    score_to_action = {
        "image_count": {
            "title": "Add more product images",
            "detail": "Top competitors have significantly more images. Add lifestyle shots, infographics, and dimension images.",
            "impact": "high",
        },
        "bullet_points": {
            "title": "Add feature bullet points to your listing",
            "detail": "Competitors use bullet points to highlight key specs. Add 5-7 clear bullet points covering capacity, charging speed, compatibility, and design.",
            "impact": "high",
        },
        "description": {
            "title": "Expand product description",
            "detail": "Your description is shorter than competitors. Include use cases, technical specs, and compatibility details.",
            "impact": "medium",
        },
        "title_keywords": {
            "title": "Optimize title with high-traffic keywords",
            "detail": "Add missing keywords from top competitors into your title and description.",
            "impact": "high",
        },
        "rating": {
            "title": "Improve product rating",
            "detail": "Your rating is below competitors. Focus on product quality and follow up with buyers for reviews.",
            "impact": "medium",
        },
        "reviews": {
            "title": "Build up review count",
            "detail": "Competitors have more reviews which boosts ranking. Run campaigns to gather genuine reviews.",
            "impact": "high",
        },
        "price": {
            "title": "Review pricing strategy",
            "detail": "Your price is higher than average competitors. Consider competitive pricing or highlight added value.",
            "impact": "medium",
        },
    }

    sorted_scores = sorted(scores.items(), key=lambda x: x[1])

    for key, score in sorted_scores:
        if score < 7.0 and key in score_to_action:
            action = score_to_action[key].copy()
            action["score"] = score
            action["key"] = key
            actions.append(action)

    return actions


# ── Roadmap to #1 ────────────────────────────────────────────────────────────

def _roadmap_to_top(yours: dict, top: dict, missing_keywords: list[str]) -> dict:
    """
    Concrete, ranked steps to outrank the current #1 competitor.
    Each step states the exact gap to close and the target to hit — derived from
    real numbers, not templates. Ordered by estimated ranking impact.
    """
    steps = []

    your_imgs = yours.get("image_count", 0) or 0
    top_imgs  = top.get("image_count", 0) or 0
    if top_imgs > your_imgs:
        steps.append({
            "area": "Images", "impact": "high",
            "title": f"Add {top_imgs - your_imgs} more product image(s)",
            "detail": f"You have {your_imgs}; the #1 competitor has {top_imgs}. "
                      f"Aim for {max(top_imgs, 7)}+ — lifestyle shots, infographics, "
                      f"dimensions, and an in-use photo. Listings with more images convert higher.",
            "target": max(top_imgs, 7),
        })

    your_revs = yours.get("review_count", 0) or 0
    top_revs  = top.get("review_count", 0) or 0
    if top_revs > your_revs:
        gap = top_revs - your_revs
        steps.append({
            "area": "Reviews", "impact": "high",
            "title": f"Close the review gap (~{gap:,} reviews behind #1)",
            "detail": f"You have {your_revs:,} reviews vs the leader's {top_revs:,}. "
                      f"Enrol in Amazon Vine, add a product-insert asking for honest reviews, "
                      f"and trigger review-request emails. Even reaching {your_revs + max(gap // 4, 10):,} "
                      f"narrows the trust gap.",
            "target": top_revs,
        })

    your_rating = yours.get("rating", 0) or 0
    top_rating  = top.get("rating", 0) or 0
    if top_rating and your_rating and your_rating + 0.1 < top_rating:
        steps.append({
            "area": "Rating", "impact": "medium",
            "title": f"Lift rating from {your_rating}★ toward {top_rating}★",
            "detail": "The #1 competitor is better rated. Audit recent negative reviews for "
                      "recurring complaints (quality, packaging, sizing) and fix the root cause; "
                      "proactively resolve issues before they become 1–2★ reviews.",
            "target": top_rating,
        })

    your_price = yours.get("price", 0) or 0
    top_price  = top.get("price", 0) or 0
    if your_price and top_price and your_price > top_price:
        diff = round(your_price - top_price)
        steps.append({
            "area": "Price", "impact": "medium",
            "title": f"You're ₹{diff} pricier than #1 — justify it or close the gap",
            "detail": f"Your ₹{your_price} vs their ₹{top_price}. Either drop toward ₹{top_price} "
                      f"(or just under), or make the premium obvious in images/bullets "
                      f"(better materials, more pieces, warranty) so the higher price reads as more value.",
            "target": top_price,
        })

    your_bullets = yours.get("bullet_count", 0) or 0
    top_bullets  = top.get("bullet_count", 0) or 0
    if top_bullets > your_bullets:
        steps.append({
            "area": "Bullets", "impact": "high",
            "title": f"Add {max(top_bullets, 5) - your_bullets} more bullet point(s)",
            "detail": f"You have {your_bullets} bullets; the leader has {top_bullets}. "
                      f"Write {max(top_bullets, 5)} benefit-led bullets covering material, "
                      f"dimensions/capacity, use-cases, what's included, and care — front-load keywords.",
            "target": max(top_bullets, 5),
        })

    if missing_keywords:
        kw = missing_keywords[:8]
        steps.append({
            "area": "Keywords", "impact": "high",
            "title": f"Add {len(kw)} high-traffic keyword(s) competitors rank for",
            "detail": "Work these into your title, bullets, and backend search terms "
                      "(don't keyword-stuff the title — front the 2–3 most relevant): "
                      + ", ".join(kw),
            "target": kw,
        })

    # Rank: high-impact first, then by the order added
    impact_rank = {"high": 0, "medium": 1, "low": 2}
    steps.sort(key=lambda s: impact_rank.get(s["impact"], 3))
    for i, s in enumerate(steps, 1):
        s["step"] = i

    # Headline summary
    top_title = (top.get("title") or "the #1 competitor")[:70]
    if not steps:
        summary = "You're already matching or beating the #1 competitor on every measured factor. " \
                  "Focus on maintaining reviews and refreshing images to hold the position."
    else:
        summary = (f"To outrank “{top_title}”, close {len(steps)} gap(s) below — "
                   f"the high-impact items (images, reviews, bullets, keywords) move ranking the most.")

    return {"summary": summary, "steps": steps,
            "top_competitor_title": top.get("title", ""),
            "top_competitor_url": top.get("url", "")}


# ── Utility ────────────────────────────────────────────────────────────────────

def _average(comps: list[dict]) -> dict:
    if not comps:
        return {}
    keys = ["image_count", "description_word_count", "bullet_count",
            "rating", "review_count", "price"]
    result = {}
    for k in keys:
        vals = [c.get(k) or 0 for c in comps]
        result[k] = round(sum(vals) / len(vals), 1)
    all_kw = [k for c in comps for k in c.get("keywords", [])]
    freq: dict[str, int] = {}
    for k in all_kw:
        freq[k] = freq.get(k, 0) + 1
    result["keywords"] = [k for k, _ in sorted(freq.items(), key=lambda x: -x[1])[:20]]
    return result
