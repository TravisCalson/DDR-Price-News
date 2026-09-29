"""daily_update.py — Generate daily DDR price snapshot, briefing, and news via Claude.

Two-phase approach:
  Phase A: Claude + web_search/web_fetch → research notes
  Phase B: Claude + structured output → DailyReport JSON

Writes:
  data/prices/YYYY-MM-DD.json
  data/briefings/YYYY-MM-DD.json
  data/news/YYYY-MM-DD.json
  data/latest.json (delegated to aggregate.py)

Usage:
  ANTHROPIC_API_KEY=... python scripts/daily_update.py [--date 2026-09-29]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent.parent / "data"
CN_TZ = ZoneInfo("Asia/Shanghai")

MODEL = "claude-opus-4-6"
MAX_RETRIES = 3
MAX_PAUSE_TURNS = 5


# === Pydantic models for structured output ===
class PriceItem(BaseModel):
    id: str
    category: str
    density: str | None = None
    spec: str | None = None
    form: str | None = None
    capacity: str | None = None
    price_usd: float | None = None
    change_dod_pct: float | None = None
    change_wow_pct: float | None = None
    currency: str = "USD"
    unit: str = ""
    period: str | None = None
    confidence: str = "medium"
    note: str | None = None


class Source(BaseModel):
    name: str
    url: str
    retrieved_at: str | None = None


class PriceSnapshot(BaseModel):
    granules: list[PriceItem]
    modules: list[PriceItem]
    contract: list[PriceItem]
    fx_usd_cny: float | None = None
    sources: list[Source] = []
    data_quality: str = "partial"
    data_quality_note: str | None = None


class Briefing(BaseModel):
    title: str
    summary: str = Field(description="<=80 Chinese chars, one sentence")
    body_markdown: str = Field(description="Sections: 价格面/供给面/厂商动态/关注点")
    price_overview_markdown: str | None = None
    supply_demand_points: list[str] = []
    outlook_markdown: str | None = None
    watch_items: list[str] = []
    bullish_points: list[str] = []
    bearish_points: list[str] = []
    confidence: str = "medium"


class NewsItem(BaseModel):
    id: str
    vendor: str
    tags: list[str] = []
    title: str
    summary: str
    url: str | None = None
    source_name: str | None = None
    published_date: str | None = None
    impact: str = "other"
    importance: str = "medium"


class News(BaseModel):
    items: list[NewsItem]


class DailyReport(BaseModel):
    price: PriceSnapshot
    briefing: Briefing
    news: News


# === Fixed series IDs ===
FIXED_IDS = """Fixed series IDs (use exactly these, never omit):
Granules: ddr4_8gbit, ddr4_16gbit, ddr5_8gbit, ddr5_16gbit
Modules: ddr4_udimm_16gb, ddr5_udimm_16gb, ddr5_rdimm_32gb, ddr5_rdimm_64gb
Contract: ddr4_8gbit_contract, ddr5_8gbit_contract"""

SYSTEM_PROMPT = f"""You are a DRAM/DDR market analyst for a hardware BOM engineer.
You collect spot and contract price quotes, module prices, and manufacturer capacity/pricing news.

Rules:
- Prefer data published within the last 7 days; clearly mark older data.
- Never invent numeric quotes. If you cannot find a quote, set price to null and explain in note / data_quality_note.
- Normalize densities to IDs like ddr4_8gbit, ddr5_16gbit (use "gbit" not "gb").
- Prices: number only, no currency symbols. Default currency USD.
  If source is CNY, convert using the rate you find and record both in note.
- change_dod_pct / change_wow_pct: compute only if you have both points; otherwise null.
- All user-facing text (title, summary, body_markdown) in Simplified Chinese.
- Vendors: Samsung / SK Hynix / Micron / CXMT / Nanya / Other.
- Include source URLs for every numeric quote and every news item.

{FIXED_IDS}"""

RESEARCH_PROMPT = """Today's date (China time): {date}
Previous trading day: {prev_date}
Previous day's snapshot (JSON):
{prev_snapshot}

Search the web and produce detailed research notes covering:
1. DDR4 & DDR5 spot prices (chip-level: 8Gb/16Gb) and module prices
   (UDIMM 16GB, RDIMM 32GB/64GB) — USD preferred, note currency if not.
2. Monthly/contract DRAM prices if reported (TrendForce, DRAMeXchange, etc.).
3. Last 48h industry news: Samsung / SK Hynix / Micron capacity plans,
   HBM (HBM3e/HBM4) crowding-out of conventional DRAM, pricing actions,
   CXMT progress, any capex or utilization changes.
4. Supply/demand signals: server vs mobile vs PC demand, inventory, order trends.

For each fact, note the source URL and publication date.
Output: structured markdown notes (no need for final JSON yet).
Do not summarize away numbers — keep every quote you find."""

EXTRACT_PROMPT = """Convert the research notes below into the DailyReport JSON matching the schema exactly.

Date: {date}

Notes:
{notes}

Additional rules for fields:
- summary: <=80 Chinese characters, one sentence.
- body_markdown: sections 价格面 / 供给面 / 厂商动态 / 关注点.
- supply_demand_points: 2-5 short Chinese bullets.
- bullish_points / bearish_points: each 0-4 bullets.
- news.items: max 12, sorted by importance (high first).
- confidence: "high" if multiple fresh sources for most quotes; "medium" if partial; "low" if mostly inferred.
- Fill ALL fixed series IDs. Use price_usd=null if not found.

{fixed_ids}"""


def get_target_date() -> str:
    """Get target date in China timezone, or use --date override."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Override date (YYYY-MM-DD, China time)")
    args = parser.parse_args()

    if args.date:
        return args.date
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def get_prev_date(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    prev = d - timedelta(days=1)
    return prev.strftime("%Y-%m-%d")


def load_prev_snapshot(prev_date: str) -> str:
    pf = DATA_DIR / "prices" / f"{prev_date}.json"
    if pf.exists():
        with open(pf, encoding="utf-8") as f:
            return f.read()
    return "(no previous data)"


def call_with_retries(client, messages_fn):
    """Call Claude with retry on 429/529."""
    for attempt in range(MAX_RETRIES):
        try:
            return messages_fn()
        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = (2 ** attempt) * 5
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} after {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def phase_a_research(client, date: str, prev_date: str, prev_snapshot: str) -> str:
    """Phase A: web search + research notes."""
    prompt = RESEARCH_PROMPT.format(
        date=date, prev_date=prev_date, prev_snapshot=prev_snapshot
    )

    messages = [{"role": "user", "content": prompt}]
    pause_count = 0

    while pause_count <= MAX_PAUSE_TURNS:
        response = call_with_retries(
            client,
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=[
                    {"type": "web_search_20260209", "name": "web_search"},
                    {"type": "web_fetch_20260209", "name": "web_fetch"},
                ],
                messages=messages,
            ),
        )

        if response.stop_reason == "pause_turn":
            # Append assistant content and continue
            messages.append({"role": "assistant", "content": response.content})
            pause_count += 1
            print(f"  Phase A: pause_turn ({pause_count}/{MAX_PAUSE_TURNS}), continuing...")
            continue

        break

    notes = "".join(
        b.text for b in response.content if b.type == "text"
    )
    return notes


def phase_b_extract(client, date: str, notes: str) -> DailyReport:
    """Phase B: structured extraction."""
    prompt = EXTRACT_PROMPT.format(
        date=date,
        notes=notes,
        fixed_ids=FIXED_IDS,
    )

    response = call_with_retries(
        client,
        lambda: client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format={
                "type": "json_schema",
                "schema": DailyReport.model_json_schema(),
            },
        ),
    )

    # Parse the structured output
    text = "".join(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return DailyReport(**data)


def ensure_fixed_ids(items: list[PriceItem], required_ids: set[str]) -> list[PriceItem]:
    """Null-pad missing fixed IDs so charts have continuous series."""
    existing = {item.id for item in items}
    for rid in required_ids - existing:
        category = "DDR4" if "ddr4" in rid else "DDR5"
        items.append(
            PriceItem(
                id=rid,
                category=category,
                price_usd=None,
                confidence="low",
                note="not found today",
            )
        )
    return items


def write_artifacts(report: DailyReport, date: str):
    now = datetime.now(ZoneInfo("UTC")).isoformat()
    generated_at = now.replace("+00:00", "Z")

    granule_ids = {"ddr4_8gbit", "ddr4_16gbit", "ddr5_8gbit", "ddr5_16gbit"}
    module_ids = {"ddr4_udimm_16gb", "ddr5_udimm_16gb", "ddr5_rdimm_32gb", "ddr5_rdimm_64gb"}
    contract_ids = {"ddr4_8gbit_contract", "ddr5_8gbit_contract"}

    report.price.granules = ensure_fixed_ids(report.price.granules, granule_ids)
    report.price.modules = ensure_fixed_ids(report.price.modules, module_ids)
    report.price.contract = ensure_fixed_ids(report.price.contract, contract_ids)

    # Price snapshot
    price_data = {
        "schema_version": 1,
        "date": date,
        "generated_at": generated_at,
        "currency_note": "USD unless currency field says otherwise",
        "granules": [item.model_dump() for item in report.price.granules],
        "modules": [item.model_dump() for item in report.price.modules],
        "contract": [item.model_dump() for item in report.price.contract],
        "fx": {"usd_cny": report.price.fx_usd_cny},
        "sources": [s.model_dump() for s in report.price.sources],
        "data_quality": report.price.data_quality,
        "data_quality_note": report.price.data_quality_note,
    }

    # Briefing
    briefing_data = {
        "schema_version": 1,
        "date": date,
        "title": report.briefing.title,
        "summary": report.briefing.summary,
        "body_markdown": report.briefing.body_markdown,
        "price_overview_markdown": report.briefing.price_overview_markdown,
        "supply_demand_points": report.briefing.supply_demand_points,
        "outlook_markdown": report.briefing.outlook_markdown,
        "watch_items": report.briefing.watch_items,
        "bullish_points": report.briefing.bullish_points,
        "bearish_points": report.briefing.bearish_points,
        "confidence": report.briefing.confidence,
        "generated_at": generated_at,
    }

    # News
    news_data = {
        "schema_version": 1,
        "date": date,
        "items": [item.model_dump() for item in report.news.items],
    }

    # Write files
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Written: {path.relative_to(DATA_DIR.parent)}")

    write(DATA_DIR / "prices" / f"{date}.json", price_data)
    write(DATA_DIR / "briefings" / f"{date}.json", briefing_data)
    write(DATA_DIR / "news" / f"{date}.json", news_data)


def main():
    date = get_target_date()
    prev_date = get_prev_date(date)

    print(f"DDR Daily Update — {date} (prev: {prev_date})")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Load previous snapshot for context
    prev_snapshot = load_prev_snapshot(prev_date)

    # Phase A: Research
    print("Phase A: web research...")
    notes = phase_a_research(client, date, prev_date, prev_snapshot)
    print(f"  Research notes: {len(notes)} chars")

    if not notes.strip():
        print("ERROR: Phase A returned empty notes")
        sys.exit(1)

    # Phase B: Structured extraction
    print("Phase B: structured extraction...")
    report = phase_b_extract(client, date, notes)
    print(f"  Granules: {len(report.price.granules)}, Modules: {len(report.price.modules)}, News: {len(report.news.items)}")

    # Write artifacts
    write_artifacts(report, date)

    print(f"Done. Next: run aggregate.py and validate.py")


if __name__ == "__main__":
    main()
