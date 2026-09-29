"""aggregate.py — Rebuild data/history.json and data/latest.json from daily files.

Idempotent: running twice produces identical output.
"""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PRICES_DIR = DATA_DIR / "prices"
BRIEFINGS_DIR = DATA_DIR / "briefings"
NEWS_DIR = DATA_DIR / "news"

# Stable series IDs (same as in prompts — charts depend on these)
SERIES_META = {
    "ddr4_8gbit": {"label": "DDR4 8Gb", "unit": "USD", "category": "DDR4"},
    "ddr4_16gbit": {"label": "DDR4 16Gb", "unit": "USD", "category": "DDR4"},
    "ddr5_8gbit": {"label": "DDR5 8Gb", "unit": "USD", "category": "DDR5"},
    "ddr5_16gbit": {"label": "DDR5 16Gb", "unit": "USD", "category": "DDR5"},
    "ddr4_udimm_16gb": {"label": "DDR4 UDIMM 16GB", "unit": "USD", "category": "DDR4"},
    "ddr5_udimm_16gb": {"label": "DDR5 UDIMM 16GB", "unit": "USD", "category": "DDR5"},
    "ddr5_rdimm_32gb": {"label": "DDR5 RDIMM 32GB", "unit": "USD", "category": "DDR5"},
    "ddr5_rdimm_64gb": {"label": "DDR5 RDIMM 64GB", "unit": "USD", "category": "DDR5"},
    "ddr4_8gbit_contract": {"label": "DDR4 8Gb 合约", "unit": "USD", "category": "DDR4"},
    "ddr5_8gbit_contract": {"label": "DDR5 8Gb 合约", "unit": "USD", "category": "DDR5"},
}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_price_points(price_data):
    """Extract {id: price_usd} from a daily snapshot."""
    points = {}
    for group in ("granules", "modules", "contract"):
        for item in price_data.get(group, []):
            sid = item.get("id")
            if sid:
                points[sid] = item.get("price_usd")
    return points


def aggregate():
    # Collect all price files sorted by date
    price_files = sorted(PRICES_DIR.glob("*.json"))
    if not price_files:
        print("No price files found, skipping aggregation.")
        return

    # Build series
    series = {sid: [] for sid in SERIES_META}
    dates_set = set()

    for pf in price_files:
        data = load_json(pf)
        date = data.get("date", pf.stem)
        dates_set.add(date)
        points = extract_price_points(data)
        for sid in SERIES_META:
            series[sid].append({"d": date, "p": points.get(sid)})

    # Sort each series by date
    for sid in series:
        series[sid].sort(key=lambda x: x["d"])

    # Build briefings index
    briefings_index = []
    for bf in sorted(BRIEFINGS_DIR.glob("*.json"), reverse=True):
        b = load_json(bf)
        briefings_index.append({
            "date": b.get("date", bf.stem),
            "title": b.get("title", ""),
            "summary": b.get("summary", ""),
            "watch_items": b.get("watch_items", []),
        })

    # Build news index
    news_index = []
    for nf in sorted(NEWS_DIR.glob("*.json"), reverse=True):
        n = load_json(nf)
        for item in n.get("items", []):
            news_index.append({
                "date": item.get("published_date", n.get("date", nf.stem)),
                "vendor": item.get("vendor", "Other"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "importance": item.get("importance", "low"),
            })

    # Sort news by date descending
    news_index.sort(key=lambda x: x["date"], reverse=True)

    # Latest date
    latest_date = max(dates_set)

    history = {
        "schema_version": 1,
        "updated": max(
            load_json(pf).get("generated_at", "")
            for pf in price_files
        ),
        "series_meta": SERIES_META,
        "series": series,
        "briefings_index": briefings_index,
        "news_index": news_index,
    }

    with open(DATA_DIR / "history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # Build latest.json
    price_data = load_json(PRICES_DIR / f"{latest_date}.json")
    briefing_path = BRIEFINGS_DIR / f"{latest_date}.json"
    news_path = NEWS_DIR / f"{latest_date}.json"

    latest = {
        "date": latest_date,
        "price": price_data,
        "briefing": load_json(briefing_path) if briefing_path.exists() else None,
        "news": load_json(news_path) if news_path.exists() else {"schema_version": 1, "date": latest_date, "items": []},
    }

    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f"Aggregated {len(price_files)} price files -> history.json")
    print(f"Latest date: {latest_date}")
    print(f"Briefings: {len(briefings_index)}, News items: {len(news_index)}")


if __name__ == "__main__":
    aggregate()
