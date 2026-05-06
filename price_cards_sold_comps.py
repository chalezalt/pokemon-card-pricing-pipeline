import csv
import os
import re
import time
import statistics
from pathlib import Path

from apify_client import ApifyClient

BASE = Path(__file__).resolve().parent
INPUT = BASE / "output/inventory_variants_final_clean.csv"
OUTPUT = BASE / "pricing/pricing_results.csv"

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
ACTOR_ID = "caffein.dev/ebay-sold-listings"

MAX_CARDS = 26

EXCLUDE_WORDS = [
    "psa", "cgc", "bgs", "beckett", "sgc", "graded", "slab", "slabbed",
    "lot", "bundle", "collection", "set of", "x4", "4x", "proxy",
    "japanese", "german", "french", "spanish", "italian", "korean",
    "sealed", "pack", "booster", "digital",
]

def variant_label(row):
    if row["variant_1st_edition"] == "YES":
        return "1st Edition"
    if row["set_name"] == "Base" and row["variant_shadowless"] == "YES":
        return "Shadowless"
    return "Unlimited"

def pricing_priority(row):
    if row["variant_1st_edition"] == "YES":
        return 1
    if row["variant_shadowless"] == "YES":
        return 2
    if row["rarity"] == "Rare":
        return 3
    if row["rarity"] == "Uncommon":
        return 4
    return 5

def build_query(row):
    variant = variant_label(row)
    parts = ["Pokemon", row["name"], row["card_number"], row["set_name"]]
    if variant in {"1st Edition", "Shadowless"}:
        parts.append(variant)
    parts.append("MP")
    return " ".join(parts)

def is_bad_comp(title):
    t = title.lower()
    return any(w in t for w in EXCLUDE_WORDS)

def numeric_price(item):
    for key in ["price", "soldPrice", "finalPrice", "currentPrice"]:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for inner in ["value", "amount"]:
                if inner in value:
                    try:
                        return float(value[inner])
                    except Exception:
                        pass
        if isinstance(value, str):
            m = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
            if m:
                return float(m.group(0))
    return None

def fetch_sold_comps(client, query):
    run_input = {"keywords": [query]}
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    dataset_id = run["defaultDatasetId"]
    return list(client.dataset(dataset_id).iterate_items())

def clean_comps(items):
    comps = []

    for item in items:
        title = item.get("title") or item.get("name") or ""
        if not title or is_bad_comp(title):
            continue

        price = numeric_price(item)
        if price is None or price <= 0:
            continue

        if price > 500:
            continue

        comps.append({
            "title": title,
            "price": price,
            "url": item.get("url") or item.get("itemUrl") or "",
            "date": item.get("soldDate") or item.get("endDate") or item.get("date") or "",
        })

    comps.sort(key=lambda x: x["price"])
    return comps[:10]

def choose_price(comps):
    if not comps:
        return "", "", "", "", "NO_COMPS"

    prices = [c["price"] for c in comps]
    low = min(prices)
    high = max(prices)
    mid = statistics.mean(prices)
    chosen = round(mid, 2)

    return f"{low:.2f}", f"{mid:.2f}", f"{high:.2f}", f"{chosen:.2f}", f"{len(comps)} comps"

def listing_bucket(row, chosen_price):
    try:
        price = float(chosen_price)
    except Exception:
        price = 0

    if row["variant_1st_edition"] == "YES" or row["variant_shadowless"] == "YES" or price >= 8:
        return "single"
    if price >= 3:
        return "maybe_single_or_small_lot"
    return "bulk"

def title_for(row, price_variant):
    parts = ["Pokemon", row["name"], row["card_number"], row["set_name"]]
    if price_variant in {"1st Edition", "Shadowless"}:
        parts.append(price_variant)
    parts += ["LP/MP", "Vintage WOTC"]
    return " ".join(parts)

def description_for(row, price_variant):
    return (
        f"{row['name']} {row['card_number']} from {row['set_name']}.\n"
        f"Variant: {price_variant}.\n"
        f"Condition estimate: LP/MP. See front and back photos for exact condition.\n"
        f"Raw card, not graded. Ships protected."
    )

def main():
    if not APIFY_TOKEN:
        raise SystemExit("Missing APIFY_TOKEN. Run: export APIFY_TOKEN='your_token'")

    client = ApifyClient(APIFY_TOKEN)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with open(INPUT, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows.sort(key=lambda r: (pricing_priority(r), r["set_name"], r["name"], r["sku"]))

    out_rows = []

    for i, row in enumerate(rows[:MAX_CARDS], 1):
        price_variant = variant_label(row)
        query = build_query(row)

        print(f"[{i}/{MAX_CARDS}] {row['sku']} {row['name']} — {query}")

        try:
            raw_items = fetch_sold_comps(client, query)
            comps = clean_comps(raw_items)
            low, mid, high, chosen, notes = choose_price(comps)
        except Exception as e:
            comps = []
            low = mid = high = chosen = ""
            notes = f"ERROR: {e}"

        out = dict(row)
        out["pricing_variant"] = price_variant
        out["pricing_search_query"] = query
        out["ebay_sold_low"] = low
        out["ebay_sold_mid"] = mid
        out["ebay_sold_high"] = high
        out["chosen_price"] = chosen
        out["listing_bucket"] = listing_bucket(row, chosen)
        out["pricing_notes"] = notes
        out["listing_title"] = title_for(row, price_variant)
        out["listing_description"] = description_for(row, price_variant)
        out["comp_titles"] = " || ".join(c["title"] for c in comps)
        out["comp_prices"] = " | ".join(f'{c["price"]:.2f}' for c in comps)

        out_rows.append(out)
        time.sleep(1)

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nSaved: {OUTPUT}")
    print(f"Priced rows: {len(out_rows)}")

if __name__ == "__main__":
    main()
