"""daily_update.py — Free web scraping version (no API key needed).

Scrapes public sources for DDR price news and generates daily artifacts.

Usage:
  python scripts/daily_update.py [--date 2026-09-29]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from datetime import timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc

import requests
from bs4 import BeautifulSoup
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
CN_TZ = CN_TZ
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Fixed series IDs
FIXED_GRANULES = ["ddr4_8gbit", "ddr4_16gbit", "ddr5_8gbit", "ddr5_16gbit"]
FIXED_MODULES = ["ddr4_udimm_16gb", "ddr5_udimm_16gb", "ddr5_rdimm_32gb", "ddr5_rdimm_64gb"]
FIXED_CONTRACT = ["ddr4_8gbit_contract", "ddr5_8gbit_contract"]

CATEGORY_MAP = {
    "ddr4": "DDR4", "ddr5": "DDR5",
}


def get_target_date() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Override date (YYYY-MM-DD, China time)")
    args = parser.parse_args()
    return args.date or datetime.now(CN_TZ).strftime("%Y-%m-%d")


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [warn] Failed to fetch {url}: {e}")
        return None


def scrape_trendforce_news() -> list[dict]:
    """Scrape TrendForce press center for DDR/DRAM news."""
    items = []
    html = fetch_page("https://www.trendforce.com/presscenter/news/")
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")
    # Find article links — skip navigation
    SKIP_TITLES = {"memory & storage", "dram spot price", "dram contract price",
                    "gddr spot price", "lpddr spot price", "mobile dram contract price",
                    "memory card spot price", "nand flash spot price", "view all"}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not title or len(title) < 15:
            continue
        if title.lower() in SKIP_TITLES:
            continue
        # Only press center articles
        if "/presscenter/" not in href and "/news/" not in href:
            continue
        # Filter DDR/DRAM related
        keywords = ["DDR", "DRAM", "HBM", "Samsung", "SK Hynix", "Micron", "Nanya", "memory", "price"]
        if any(kw.lower() in title.lower() for kw in keywords):
            url = href if href.startswith("http") else f"https://www.trendforce.com{href}"
            items.append({
                "title": title,
                "url": url,
                "source": "TrendForce",
            })

    return items[:10]


def scrape_chinaflashmarket() -> list[dict]:
    """Try ChinaFlashMarket for spot price data."""
    items = []
    html = fetch_page("https://www.chinaflashmarket.com/")
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    # Look for DDR price patterns
    for line in text.split("\n"):
        line = line.strip()
        if any(kw in line.upper() for kw in ["DDR4", "DDR5"]) and any(c.isdigit() for c in line):
            items.append({"text": line, "source": "ChinaFlashMarket"})

    return items[:10]


def extract_prices_from_text(text: str) -> dict:
    """Try to extract price numbers from text. Only reasonable USD prices."""
    prices = {}
    # Skip speed specs (3200, 4800, 5600, 6400 etc.) — those are MHz not prices
    SKIP_VALUES = {3200, 4800, 5600, 6400, 8000, 2666, 2400, 2133, 1866, 1600}

    def is_real_price(val: float) -> bool:
        if val in SKIP_VALUES:
            return False
        if val < 0.1 or val > 1000:
            return False
        return True

    patterns = [
        (r'DDR4\s*8Gb[^\d$]*?[\$]?(\d+\.?\d*)', 'ddr4_8gbit'),
        (r'DDR4\s*16Gb[^\d$]*?[\$]?(\d+\.?\d*)', 'ddr4_16gbit'),
        (r'DDR5\s*8Gb[^\d$]*?[\$]?(\d+\.?\d*)', 'ddr5_8gbit'),
        (r'DDR5\s*16Gb[^\d$]*?[\$]?(\d+\.?\d*)', 'ddr5_16gbit'),
    ]
    for pat, sid in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val = float(m.group(1))
            if is_real_price(val):
                prices[sid] = val
                break

    return prices


def make_price_item(id: str, price: Optional[float] = None, **kw) -> dict:
    cat = "DDR4" if "ddr4" in id else "DDR5"
    density = kw.get("density", "")
    form = kw.get("form", "")
    capacity = kw.get("capacity", "")
    return {
        "id": id,
        "category": cat,
        "density": density or None,
        "spec": kw.get("spec"),
        "form": form or None,
        "capacity": capacity or None,
        "price_usd": price,
        "change_dod_pct": kw.get("change_dod_pct"),
        "change_wow_pct": kw.get("change_wow_pct"),
        "currency": "USD",
        "unit": kw.get("unit", "per chip"),
        "period": kw.get("period"),
        "confidence": kw.get("confidence", "low" if price is None else "medium"),
        "note": kw.get("note"),
    }


def build_price_snapshot(news_items: list[dict], date: str) -> dict:
    """Build price snapshot from scraped data."""
    # Combine all text for price extraction
    all_text = " ".join(item.get("title", "") + " " + item.get("text", "") for item in news_items)
    found_prices = extract_prices_from_text(all_text)

    granules = [
        make_price_item("ddr4_8gbit", found_prices.get("ddr4_8gbit"), density="8Gb", spec="3200"),
        make_price_item("ddr4_16gbit", found_prices.get("ddr4_16gbit"), density="16Gb", spec="3200"),
        make_price_item("ddr5_8gbit", found_prices.get("ddr5_8gbit"), density="8Gb", spec="4800-5600"),
        make_price_item("ddr5_16gbit", found_prices.get("ddr5_16gbit"), density="16Gb", spec="4800-6400"),
    ]
    modules = [
        make_price_item("ddr4_udimm_16gb", found_prices.get("ddr4_udimm_16gb"),
                        form="UDIMM", capacity="16GB", spec="3200", unit="per module"),
        make_price_item("ddr5_udimm_16gb", found_prices.get("ddr5_udimm_16gb"),
                        form="UDIMM", capacity="16GB", spec="4800/5600", unit="per module"),
        make_price_item("ddr5_rdimm_32gb", found_prices.get("ddr5_rdimm_32gb"),
                        form="RDIMM", capacity="32GB", spec="4800/5600", unit="per module"),
        make_price_item("ddr5_rdimm_64gb", None,
                        form="RDIMM", capacity="64GB", spec="4800/5600", unit="per module"),
    ]
    contract = [
        make_price_item("ddr4_8gbit_contract", None, density="8Gb", period=f"{date[:7]} monthly", unit="per chip"),
        make_price_item("ddr5_8gbit_contract", None, density="8Gb", period=f"{date[:7]} monthly", unit="per chip"),
    ]

    has_any_price = any(p["price_usd"] is not None for p in granules + modules)
    return {
        "schema_version": 1,
        "date": date,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "currency_note": "USD unless currency field says otherwise",
        "granules": granules,
        "modules": modules,
        "contract": contract,
        "fx": {"usd_cny": None},
        "sources": [{"name": item.get("source", ""), "url": item.get("url", ""), "retrieved_at": date}
                     for item in news_items[:5] if item.get("url")],
        "data_quality": "partial" if has_any_price else "low",
        "data_quality_note": None if has_any_price else "今日未能从公开源抓取到确切价格",
    }


def build_news_items(news_items: list[dict], date: str) -> list[dict]:
    """Convert scraped news to our schema."""
    items = []
    for i, item in enumerate(news_items[:12]):
        title = item.get("title", item.get("text", ""))
        if not title or len(title) < 5:
            continue
        # Detect vendor
        vendor = "Other"
        for v in ["Samsung", "SK Hynix", "Micron", "CXMT", "Nanya"]:
            if v.lower() in title.lower():
                vendor = v
                break
        items.append({
            "id": f"{date}-news-{i}",
            "vendor": vendor,
            "tags": [],
            "title": title[:200],
            "summary": item.get("text", item.get("title", ""))[:500],
            "url": item.get("url"),
            "source_name": item.get("source", ""),
            "published_date": date,
            "impact": "other",
            "importance": "medium" if i < 3 else "low",
        })
    return items


def build_briefing(price_data: dict, news_items: list[dict], date: str) -> dict:
    """Build a simple briefing from scraped data."""
    # Count prices found
    found = sum(1 for p in price_data["granules"] + price_data["modules"] if p["price_usd"] is not None)
    total = len(price_data["granules"]) + len(price_data["modules"])

    news_titles = [item.get("title", "") for item in news_items[:5]]
    news_section = "\n".join(f"- {t}" for t in news_titles) if news_titles else "- 暂无相关新闻"

    body = f"""## 价格面

今日从公开渠道采集到 {found}/{total} 个规格的价格数据。{price_data.get('data_quality_note') or ''}

## 供给面

暂无自动分析（爬虫版仅采集原始数据）。

## 厂商动态

{news_section}

## 关注点

- 价格数据来源于公开渠道，可能存在延迟
- 建议交叉验证 TrendForce、DRAMeXchange 等专业渠道报价"""

    return {
        "schema_version": 1,
        "date": date,
        "title": f"DDR早报 {date}",
        "summary": f"爬虫版早报：采集到 {found}/{total} 个价格点，{len(news_items)} 条行业动态。",
        "body_markdown": body,
        "price_overview_markdown": f"今日采集价格 {found}/{total} 个规格。",
        "supply_demand_points": ["爬虫版暂不提供供需分析"],
        "outlook_markdown": None,
        "watch_items": [item.get("title", "")[:50] for item in news_items[:3]],
        "bullish_points": [],
        "bearish_points": [],
        "confidence": "low",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Written: {path.relative_to(DATA_DIR.parent)}")


def main():
    date = get_target_date()
    print(f"DDR Daily Update (scraper) — {date}")

    # Scrape news
    print("Scraping TrendForce...")
    news = scrape_trendforce_news()
    print(f"  Found {len(news)} items")

    print("Scraping ChinaFlashMarket...")
    cf_news = scrape_chinaflashmarket()
    news.extend(cf_news)
    print(f"  Found {len(cf_news)} price lines")

    if not news:
        print("  [warn] No news found, generating empty artifacts")

    # Build artifacts
    price_data = build_price_snapshot(news, date)
    news_data = {"schema_version": 1, "date": date, "items": build_news_items(news, date)}
    briefing_data = build_briefing(price_data, news, date)

    # Write
    write_json(DATA_DIR / "prices" / f"{date}.json", price_data)
    write_json(DATA_DIR / "briefings" / f"{date}.json", briefing_data)
    write_json(DATA_DIR / "news" / f"{date}.json", news_data)

    print("Done. Next: run aggregate.py and validate.py")


if __name__ == "__main__":
    main()
