"""
Shared "same-product, best-seller" competitor matcher.

Both the dashboard analyzer (app.py) and the bulk Excel builder (compare_all.py)
import pick_best_competitor() from here so they agree on WHICH competitor a
product is benchmarked against. Previously each had its own logic and the
dashboard simply took the most-reviewed result — which was often a different
product than ours. This module fixes that:

  * requires the competitor to genuinely be the SAME product (shared product
    words / head noun), not just the same loose category, and
  * among same-product peers, prefers the best-selling, well-rated one.

It has no dependency on app.py (the category filter is passed in), so importing
it never creates a cycle.

LEARNING FROM HUMAN CORRECTIONS
-------------------------------
competitor_references.json maps OUR product's ASIN -> the human-verified
"accurate" competitor ASIN. When a product has a reference, the comparison uses
THAT exact competitor (scraped live) instead of auto-picking — ground truth wins.
Add entries there over time (from the 'accurate link' column in the review Excel)
to make results progressively more accurate, including for brand-new products via
the title-match weighting these examples informed.
"""

import json
import os
import re

_REF_PATH = os.path.join(os.path.dirname(__file__), "competitor_references.json")
_REFERENCES = None


def load_references() -> dict:
    """ASIN -> {'accurate_asin': ...} of human-verified competitors (cached)."""
    global _REFERENCES
    if _REFERENCES is None:
        try:
            with open(_REF_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            _REFERENCES = {k: v for k, v in raw.items() if not k.startswith("_")}
        except Exception:
            _REFERENCES = {}
    return _REFERENCES


def reference_asin_for(our_asin: str) -> str | None:
    """The human-verified competitor ASIN for our product, if one was provided."""
    ref = load_references().get(our_asin or "")
    return ref.get("accurate_asin") if ref else None


# ── Word helpers ─────────────────────────────────────────────────────────────

# Generic words that don't identify a specific product.
_STOP = {
    "lazer", "set", "kit", "pack", "pcs", "pc", "piece", "pieces", "in",
    "for", "with", "and", "the", "professional", "premium", "travel", "size",
    "large", "small", "mini", "portable", "tier", "stainless", "steel",
    "leak", "proof", "leakproof", "men", "women", "girls", "boys", "new",
    "pure", "complete", "multi", "purpose", "non", "woven", "foldable",
    "accessories", "disposable", "reusable", "eco", "friendly", "ultra",
    "heavy", "duty", "soft", "plush", "waterproof", "bpa", "free",
    "of", "high", "quality", "durable", "design", "color", "colour",
    "black", "blue", "grey", "gray", "white", "red", "green", "pink",
    "home", "kitchen", "office", "outdoor", "indoor", "use", "easy",
}


def _as_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _as_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _content_words(title: str) -> set:
    """Significant, product-identifying words in a title (lowercased, singularized)."""
    out = set()
    for w in re.findall(r"\b[a-z]{3,}\b", (title or "").lower()):
        if w in _STOP:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _head_words(title: str, n: int = 4) -> list:
    """The first `n` product-identifying words, in order — the product name lives
    at the FRONT of an Amazon title (features come after a '|' or ',')."""
    out = []
    for w in re.findall(r"\b[a-z]{3,}\b", (title or "").lower()):
        if w in _STOP:
            continue
        out.append(w[:-1] if w.endswith("s") and len(w) > 4 else w)
        if len(out) >= n:
            break
    return out


def overlap_score(our_title: str, comp_title: str) -> int:
    """Shared product-identifying words, plus a big bonus when the competitor
    shares one of OUR leading head words (the actual product name) — so trailing
    material/adjective overlap alone ('wheat straw') can't pass as the same product."""
    comp_words = _content_words(comp_title)
    score = len(_content_words(our_title) & comp_words)
    if set(_head_words(our_title)) & comp_words:
        score += 5
    return score


def is_junk(c: dict) -> bool:
    """Drop broken scrapes: 1-2 word titles (bare brand names like 'Storite'),
    or rows with no price AND no rating (nothing to compare)."""
    title = (c.get("title") or "")
    if len(re.findall(r"\b\w+\b", title)) < 3:
        return True
    if _as_float(c.get("price")) <= 0 and _as_float(c.get("rating")) <= 0:
        return True
    return False


def search_query(title: str, max_words: int = 10) -> str:
    """Build a rich Amazon search query from the FULL product title (not just the
    first 5 words) so Amazon's own relevance returns the exact product.

    We strip the brand, dimensions ('45x33x22 cm'), pack-size noise ('set of 6'),
    and punctuation, but KEEP all the descriptive product words ('non woven
    foldable saree cover wardrobe organizer'). Capped at max_words because a
    verbatim full title is over-specific and can return zero results.
    """
    t = (title or "").lower()
    t = re.sub(r"\(.*?\)", " ", t)                       # drop "(45x33x22 cm)" etc.
    t = re.sub(r"\b\d+\s*[x×]\s*\d+(\s*[x×]\s*\d+)?\b", " ", t)   # bare dimensions
    t = re.sub(r"\b\d+\s*(cm|mm|ml|l|ltr|litre|liter|inch|in|g|kg|pcs?|pack|set)\b",
               " ", t)                                   # sized units / counts
    words, seen = [], set()
    for w in re.findall(r"\b[a-z]{3,}\b", t):
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        words.append(w)
        if len(words) >= max_words:
            break
    return " ".join(words)


# ── The picker ───────────────────────────────────────────────────────────────

GOOD_RATING = 4.0


# ── Product-TYPE gate ────────────────────────────────────────────────────────
# Many titles stuff in generic words ("storage", "organizer", "wardrobe") that
# match unrelated products (a saree COVER vs a rigid storage BOX). A specific
# product-type phrase is far more reliable than single words, so when our title
# clearly belongs to a type, the competitor MUST belong to the same type — this
# stops "Saree Cover/Wardrobe Organizer" from matching a "Steel Frame Storage Box".
#
# Each entry: canonical type -> list of phrases/words that imply it. Order matters
# only for readability; a title can match several, and we keep the most specific.
_PRODUCT_TYPES = [
    # Rigid LITRE-sized boxes with a frame/lid are a different product from soft
    # fabric covers — even when the box title also lists "saree" as a use-case.
    # Listed before saree_cover so a "Steel Frame ... Saree ... Box" classifies as
    # a box, not a cover.
    ("storage_box",   ["steel frame", "metal frame", "storage box", "organizer box",
                       "storage organizer box", "wardrobe organizer box",
                       "ltr", "litre", "liter", "foldable box", "with lid"]),
    ("saree_cover",   ["saree cover", "sari cover", "saree bag", "saree storage",
                       "saree organizer", "saree organiser", "non-woven saree",
                       "non woven saree"]),
    ("vacuum_bag",    ["vacuum bag", "vacuum storage", "compression bag"]),
    ("underbed_bag",  ["underbed", "under bed", "under-bed"]),
    ("laundry",       ["laundry bag", "laundry basket", "laundry hamper"]),
    ("manicure",      ["manicure", "pedicure", "nail clipper", "nail kit", "grooming kit"]),
    ("makeup_org",    ["makeup organizer", "cosmetic organizer", "vanity organizer",
                       "makeup organiser"]),
    ("travel_bottle", ["travel bottle", "refillable bottle", "dispenser bottle",
                       "toiletry bottle", "travel bottles"]),
    ("toiletry_kit",  ["toiletry kit", "toiletry bag", "travel kit", "toiletries kit"]),
    ("lunch_box",     ["lunch box", "tiffin", "bento", "lunch bag", "lunch kit"]),
    ("neck_pillow",   ["neck pillow", "travel pillow"]),
    ("cutting_board", ["cutting board", "chopping board"]),
    ("car_dustbin",   ["car dustbin", "car trash", "car bin", "car waste"]),
    ("air_fryer_liner", ["air fryer liner", "fryer paper", "fryer liner", "parchment liner"]),
    # Learned from human-verified corrections (the 'accurate link' column):
    ("fridge_container", ["fridge storage", "fridge container", "fridge organizer",
                          "refrigerator container", "food storage container"]),
    ("interlock_divider", ["interlocking", "adjustable strips", "drawer divider"]),
    ("jewellery_org",  ["jewellery organiser", "jewelry organizer", "jewellery box",
                        "jewelry box", "jewelry case", "jewellery case"]),
]


def product_type(title: str) -> str | None:
    """The most specific product type our/their title belongs to, or None.

    Multi-word phrases win over generic single words, and the EARLIEST-mentioned
    specific type in the title wins (Amazon leads with the real product, e.g.
    'Saree Cover/...Wardrobe Organizer' is a saree_cover, not a storage_box)."""
    t = " " + (title or "").lower() + " "
    hits = []
    for canon, phrases in _PRODUCT_TYPES:
        for ph in phrases:
            idx = t.find(ph)
            if idx != -1:
                hits.append((idx, canon))
                break
    if not hits:
        return None
    hits.sort()                 # earliest mention first = the lead product
    return hits[0][1]


def same_product_candidates(our_title: str, competitors: list) -> list:
    """Keep only competitors that are genuinely the SAME product as ours.

    1. If our title has a clear product TYPE, require the competitor to share it
       (a saree cover only matches saree covers, never a storage box).
    2. Otherwise fall back to shared product-identifying words / head noun.
    Returns the gated list (may be empty -> no genuine peer found).
    """
    competitors = [c for c in competitors if not is_junk(c)]
    if not competitors:
        return []

    our_type = product_type(our_title)
    if our_type:
        typed = [c for c in competitors if product_type(c.get("title", "")) == our_type]
        if typed:
            competitors = typed
        # If NOTHING shares our specific type, don't silently match a different
        # type — fall through to word overlap, which will usually also reject it.

    scored = [(c, overlap_score(our_title, c.get("title", ""))) for c in competitors]
    best = max((s for _, s in scored), default=0)
    if best >= 2:
        keep = [c for c, s in scored if s >= 2]
    elif best == 1:
        keep = [c for c, s in scored if s >= 1]
    else:
        keep = []     # nothing shares a product word -> not the same product
    return keep


def _combined_key(our_title: str):
    """Rank by title-match quality FIRST, then best-seller popularity.

    Human corrections showed the bot was right about the *set* of same-product
    candidates but wrong about WHICH — it let a slightly-more-popular but worse
    title match win (e.g. a generic 'air tight container' over a true 'fridge
    storage container'). So a clearly-better title match (overlap) now leads;
    popularity only breaks ties among comparably-good matches.
    """
    def key(c):
        ov = overlap_score(our_title, c.get("title", ""))
        # Bucket overlap so small noise doesn't dominate, but a real gap (>=2) does.
        ov_bucket = ov // 2
        r = _as_float(c.get("rating"))
        n = _as_int(c.get("review_count"))
        badged = bool(c.get("has_best_seller_badge") or c.get("has_choice_badge"))
        tier = 2 if (badged and r >= GOOD_RATING) else (1 if r >= GOOD_RATING else 0)
        popularity = r * (n ** 0.5)
        return (ov_bucket, tier, popularity, n)
    return key


def pick_best_competitor(our: dict, competitors: list, filter_fn=None) -> dict | None:
    """Pick the SAME-product, best-selling, well-rated competitor to benchmark against.

    Order of precedence:
      1. HUMAN REFERENCE — if competitor_references.json names an accurate
         competitor ASIN for our product and it's in the candidate list, use it.
      2. Otherwise auto-pick: same-product gate, then rank by title-match quality
         first and best-seller popularity second.

    filter_fn: optional callable(our, competitors) -> (filtered, warnings), e.g.
               app._filter_competitors, applied first to drop own-brand/self/off-category.
    Returns the chosen competitor dict, or None if there's no genuine same-product peer.
    """
    # 1. Honor a human-verified reference if its ASIN is among the candidates.
    ref = reference_asin_for(our.get("asin", ""))
    if ref:
        for c in competitors:
            url = c.get("url", "") or ""
            if ref in url or c.get("asin") == ref:
                return c

    if filter_fn is not None:
        competitors, _ = filter_fn(our, competitors)
    if not competitors:
        return None

    our_title = our.get("title", "")
    candidates = same_product_candidates(our_title, competitors)
    if not candidates:
        return None

    return sorted(candidates, key=_combined_key(our_title), reverse=True)[0]
