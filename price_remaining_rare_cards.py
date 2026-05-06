import csv
import os
import re
import time
import statistics
from pathlib import Path
from apify_client import ApifyClient

BASE = Path(__file__).resolve().parent
INPUT = BASE / "pricing/pricing_results_cleaned.csv"
OUTPUT = BASE / "pricing/pricing_results_26_complete.csv"

ACTOR_ID = "caffein.dev/ebay-sold-listings"

EXCLUDE_WORDS = [
    "psa", "cgc", "bgs", "beckett", "sgc", "graded", "slab", "slabbed",
    "lot", "bundle", "collection", "set of", "x4", "4x", "proxy",
    "japanese", "german", "french", "spanish", "italian", "korean",
    "sealed", "pack", "booster", "digital",
]

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

        # remove obvious junk auction/outlier comps
        if price < 0.50:
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

def choose_price(comps, row):
    if not comps:
        return "", "", "", "", "NO_COMPS"

    prices = [c["price"] for c in comps]
    low = min(prices)
    high = max(prices)
    mid = statistics.mean(prices)

    if row["variant_shadowless"] == "YES":
        chosen = mid
        bucket = "single"
    elif row["variant_1st_edition"] == "YES":
        chosen = max(1.49, mid)
        bucket = "single_or_1st_ed_group"
    else:
        chosen = mid
        bucket = "single" if mid >= 5 else "bulk_or_lot"

    return f"{low:.2f}", f"{mid:.2f}", f"{high:.2f}", f"{chosen:.2f}", bucket

token = os.environ.get("APIFY_TOKEN", "").strip()
if not token:
    raise SystemExit("Missing APIFY_TOKEN")

client = ApifyClient(token)

with open(INPUT, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    fieldnames = reader.fieldnames

to_price = [
    r for r in rows
    if not r.get("chosen_price")
    or "NOT_PRICED_APIFY_LIMIT" in r.get("pricing_notes", "")
    or "ERROR" in r.get("pricing_notes", "")
]

print(f"Rows needing pricing: {len(to_price)}")

for i, row in enumerate(to_price, 1):
    query = row["pricing_search_query"]
    print(f"[{i}/{len(to_price)}] {row['sku']} {row['name']} — {query}")

    try:
        raw_items = fetch_sold_comps(client, query)
        comps = clean_comps(raw_items)

        low, mid, high, chosen, bucket = choose_price(comps, row)

        row["ebay_sold_low"] = low
        row["ebay_sold_mid"] = mid
        row["ebay_sold_high"] = high
        row["chosen_price"] = chosen
        row["listing_bucket"] = bucket
        row["pricing_notes"] = f"{len(comps)} cleaned raw sold comps; removed graded/lots/foreign/under-$0.50 comps."
        row["comp_titles"] = " || ".join(c["title"] for c in comps)
        row["comp_prices"] = " | ".join(f'{c["price"]:.2f}' for c in comps)

    except Exception as e:
        row["pricing_notes"] = f"ERROR: {e}"

    time.sleep(1)

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nSaved: {OUTPUT}")
