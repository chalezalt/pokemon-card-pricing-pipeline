# Pokémon Card Inventory & Pricing Pipeline

A Python workflow for organizing scanned Pokémon card images into a structured inventory, enriching the inventory with pricing references, and sorting cards into practical selling buckets.

This project was built around a real 450-card vintage Pokémon collection. The goal was not to guarantee perfect valuation, but to create a repeatable resale-triage workflow: identify what is worth listing individually, what belongs in small lots, and what should be treated as bulk.

## What It Does

- Organizes cropped front/back card images by binder and card number
- Maintains a clean CSV inventory of identified cards
- Tracks card name, set, card number, rarity, condition assumptions, and variant flags
- Checks for variants such as 1st Edition, Shadowless, Unlimited, and promo cards
- Enriches inventory rows with Pokémon TCG / TCGplayer-style reference pricing
- Adds sold-comp pricing where available
- Assigns practical listing buckets: `single`, `small_lot_or_single`, `single_or_1st_ed_group`, `bulk_or_lot`, `bulk`
- Exports seller-ready CSV files

## Final Dataset Summary

- 450 total cards
- 2 binders
- 225 cards per binder
- 147 cards with usable price references
- 303 cards treated as bulk or unpriced
- Final seller-focused output: `pricing/all_cards_simple_prices.csv`

## Key Files

- `output/inventory_variants_final_clean.csv` - clean inventory with identification and variant fields
- `pricing/pricing_full_with_tcg_reference.csv` - full pricing-enriched output with reference prices, sold-comp fields, listing buckets, pricing notes, and listing text fields
- `pricing/all_cards_simple_prices.csv` - simplified seller-ready pricing file
- `price_remaining_with_pokemontcg_api.py` - adds Pokémon TCG / TCGplayer-style reference pricing
- `price_cards_sold_comps.py` - sold-comp pricing workflow
- `price_remaining_rare_cards.py` - additional targeted pricing pass

## Example Output

```text
sku,name,set_name,card_number,price,listing_bucket
B02-C013,Beedrill,Base,17/102,16.63,single
B02-C207,Pikachu,Base,58/102,7.27,single
B01-C053,Squirtle,Base,63/102,7.18,single
B01-C210,Rocket's Sneak Attack,Team Rocket,72/82,4.30,bulk_or_lot
B02-C041,Voltorb,Base,67/102,3.28,small_lot_or_single