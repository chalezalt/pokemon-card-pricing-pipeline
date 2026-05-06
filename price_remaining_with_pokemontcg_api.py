import csv
import time
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parent

FULL_INPUT = BASE / "output/inventory_variants_final_clean.csv"
APIFY_INPUT = BASE / "pricing/pricing_results_26_complete.csv"
OUTPUT = BASE / "pricing/pricing_full_with_tcg_reference.csv"

SET_MAP = {
    "Base": "base1",
    "Jungle": "base2",
    "Fossil": "base3",
    "Base Set 2": "base4",
    "Team Rocket": "base5",
    "Gym Challenge": "gym2",
    "Neo Genesis": "neo1",
    "Neo Discovery": "neo2",
    "Neo Revelation": "neo3",
    "HS—Triumphant": "hgss4",
}

def variant_label(row):
    if row["variant_1st_edition"] == "YES":
        return "1st Edition"
    if row["variant_shadowless"] == "YES":
        return "Shadowless"
    return "Unlimited"

def search_card(row):
    set_id = SET_MAP.get(row["set_name"])
    number = row["card_number"].split("/")[0].strip()
    name = row["name"].replace('"', '\\"')

    if set_id:
        q = f'name:"{name}" set.id:{set_id} number:{number}'
    else:
        q = f'name:"{name}" number:{number}'

    url = "https://api.pokemontcg.io/v2/cards"
    r = requests.get(url, params={"q": q, "pageSize": 5}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])

    if not data:
        return None

    return data[0]

def get_tcg_price(card, row):
    if not card:
        return "", "NO_TCG_MATCH"

    prices = card.get("tcgplayer", {}).get("prices", {}) or {}

    variant = variant_label(row)

    candidates = []

    if row["variant_1st_edition"] == "YES":
        candidates = [
            prices.get("1stEditionNormal"),
            prices.get("1stEditionHolofoil"),
        ]
    elif row["variant_shadowless"] == "YES":
        candidates = [
            prices.get("normal"),
            prices.get("holofoil"),
        ]
    else:
        candidates = [
            prices.get("normal"),
            prices.get("holofoil"),
            prices.get("reverseHolofoil"),
        ]

    for p in candidates:
        if not isinstance(p, dict):
            continue

        for key in ["market", "low", "mid"]:
            val = p.get(key)
            if isinstance(val, (int, float)):
                return f"{val:.2f}", f"TCGPLAYER_{key.upper()}"

    return "", "NO_TCG_PRICE"

def bucket(row, price):
    try:
        p = float(price)
    except:
        p = 0

    if row["variant_1st_edition"] == "YES" or row["variant_shadowless"] == "YES":
        return "single_or_special_lot"
    if p >= 5:
        return "single"
    if p >= 2:
        return "small_lot_or_single"
    return "bulk"

def title_for(row):
    variant = variant_label(row)
    parts = ["Pokemon", row["name"], row["card_number"], row["set_name"]]
    if variant in {"1st Edition", "Shadowless"}:
        parts.append(variant)
    parts.append("LP/MP")
    return " ".join(parts)

def description_for(row):
    variant = variant_label(row)
    return (
        f"{row['name']} {row['card_number']} from {row['set_name']}.\n"
        f"Variant: {variant}.\n"
        f"Condition estimate: LP/MP. See front and back photos for exact condition.\n"
        f"Raw card, not graded."
    )

# Load Apify-priced rows by SKU.
apify_by_sku = {}
if APIFY_INPUT.exists():
    with open(APIFY_INPUT, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("chosen_price"):
                apify_by_sku[r["sku"]] = r

with open(FULL_INPUT, newline="", encoding="utf-8") as f:
    full_rows = list(csv.DictReader(f))

out_rows = []

for i, row in enumerate(full_rows, 1):
    sku = row["sku"]
    out = dict(row)

    out["pricing_variant"] = variant_label(row)
    out["pricing_search_query"] = f'Pokemon {row["name"]} {row["card_number"]} {row["set_name"]} {out["pricing_variant"]} MP'
    out["tcgplayer_market_price"] = ""
    out["tcg_reference_note"] = ""
    out["ebay_sold_low"] = ""
    out["ebay_sold_mid"] = ""
    out["ebay_sold_high"] = ""
    out["chosen_price"] = ""
    out["listing_bucket"] = ""
    out["pricing_notes"] = ""
    out["listing_title"] = title_for(row)
    out["listing_description"] = description_for(row)

    if sku in apify_by_sku:
        priced = apify_by_sku[sku]
        out["ebay_sold_low"] = priced.get("ebay_sold_low", "")
        out["ebay_sold_mid"] = priced.get("ebay_sold_mid", "")
        out["ebay_sold_high"] = priced.get("ebay_sold_high", "")
        out["chosen_price"] = priced.get("chosen_price", "")
        out["listing_bucket"] = priced.get("listing_bucket", "")
        out["pricing_notes"] = "APIFY_SOLD_COMPS_PRIORITY_CARD"
        out["comp_titles"] = priced.get("comp_titles", "")
        out["comp_prices"] = priced.get("comp_prices", "")
    else:
        try:
            card = search_card(row)
            tcg_price, note = get_tcg_price(card, row)
            out["tcgplayer_market_price"] = tcg_price
            out["tcg_reference_note"] = note

            if tcg_price:
                # Conservative for LP/MP: use about 70% of TCG reference, minimum bulk handling later.
                chosen = round(float(tcg_price) * 0.70, 2)
                out["chosen_price"] = f"{chosen:.2f}"
                out["listing_bucket"] = bucket(row, chosen)
                out["pricing_notes"] = "TCG_API_REFERENCE_ESTIMATE_70_PERCENT_FOR_LP_MP"
            else:
                out["chosen_price"] = ""
                out["listing_bucket"] = "bulk"
                out["pricing_notes"] = note

            out["comp_titles"] = ""
            out["comp_prices"] = ""

        except Exception as e:
            out["listing_bucket"] = "bulk"
            out["pricing_notes"] = f"TCG_API_ERROR: {e}"
            out["comp_titles"] = ""
            out["comp_prices"] = ""

        time.sleep(0.15)

    out_rows.append(out)

fieldnames = list(out_rows[0].keys())

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(out_rows)

print(f"Saved: {OUTPUT}")
print(f"Rows: {len(out_rows)}")

priced = sum(1 for r in out_rows if r.get("chosen_price"))
apify = sum(1 for r in out_rows if r.get("pricing_notes") == "APIFY_SOLD_COMPS_PRIORITY_CARD")
tcg = sum(1 for r in out_rows if "TCG_API_REFERENCE" in r.get("pricing_notes", ""))
bulk = sum(1 for r in out_rows if r.get("listing_bucket") == "bulk")

print("Priced rows:", priced)
print("Apify sold-comp rows:", apify)
print("TCG API reference rows:", tcg)
print("Bulk bucket rows:", bulk)
