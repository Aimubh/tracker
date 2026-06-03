"""
Gap analyzer — compares your product against top competitors.
Produces scores, gaps, and a prioritized action list.
"""


def analyze(your_product: dict, competitors: list[dict]) -> dict:
    if not competitors:
        return {"error": "No competitor data available"}

    top = competitors[0]
    avg = _average(competitors)

    scores = {
        "title_keywords":  _score_keywords(your_product, competitors),
        "image_count":     _score_images(your_product, avg),
        "description":     _score_description(your_product, avg),
        "price":           _score_price(your_product, competitors),
        "rating":          _score_rating(your_product, avg),
        "reviews":         _score_reviews(your_product, avg),
        "bullet_points":   _score_bullets(your_product, avg),
    }

    gaps = _compute_gaps(your_product, top, avg)
    missing_keywords = _missing_keywords(your_product, competitors)
    actions = _priority_actions(gaps, scores)

    return {
        "your_product": your_product,
        "top_competitor": top,
        "avg_competitor": avg,
        "competitors": competitors,
        "competitors_count": len(competitors),
        "scores": scores,
        "gaps": gaps,
        "missing_keywords": missing_keywords,
        "priority_actions": actions,
        "overall_score": round(sum(scores.values()) / len(scores), 1),
    }


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

        # For price, lower is better; for others, higher is better
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

    # Keywords that appear in 2+ competitors but not in yours
    missing = [k for k, freq in comp_kw_freq.items()
               if freq >= 2 and k not in your_kw]
    return sorted(missing, key=lambda k: -comp_kw_freq[k])[:15]


def _priority_actions(gaps: list[dict], scores: dict) -> list[dict]:
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

    # Sort by score ascending (worst scores = highest priority)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1])

    for key, score in sorted_scores:
        if score < 7.0 and key in score_to_action:
            action = score_to_action[key].copy()
            action["score"] = score
            action["key"] = key
            actions.append(action)

    return actions


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
    # Average keywords list
    all_kw = [k for c in comps for k in c.get("keywords", [])]
    freq: dict[str, int] = {}
    for k in all_kw:
        freq[k] = freq.get(k, 0) + 1
    result["keywords"] = [k for k, _ in sorted(freq.items(), key=lambda x: -x[1])[:20]]
    return result
