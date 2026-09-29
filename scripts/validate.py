"""validate.py — JSON Schema validation for all data artifacts.

Exit 0 = all valid, exit 1 = validation errors found.
"""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)

DATA_DIR = Path(__file__).parent.parent / "data"
SCHEMA_DIR = Path(__file__).parent / "schema"

# Fixed series IDs that must appear in every price snapshot
REQUIRED_IDS = {
    "ddr4_8gbit", "ddr4_16gbit", "ddr5_8gbit", "ddr5_16gbit",
    "ddr4_udimm_16gb", "ddr5_udimm_16gb", "ddr5_rdimm_32gb", "ddr5_rdimm_64gb",
    "ddr4_8gbit_contract", "ddr5_8gbit_contract",
}


def load_schema(name):
    with open(SCHEMA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_file(path, schema, label):
    errors = []
    try:
        data = load_json(path)
    except json.JSONDecodeError as e:
        errors.append(f"{path.name}: Invalid JSON — {e}")
        return errors

    validator = jsonschema.Draft7Validator(schema)
    for err in validator.iter_errors(data):
        errors.append(f"{path.name}: {err.message} (at {'/'.join(str(p) for p in err.absolute_path)})")

    return errors


def validate_price_ids(path):
    """Check that all required series IDs are present."""
    errors = []
    data = load_json(path)
    all_ids = set()
    for group in ("granules", "modules", "contract"):
        for item in data.get(group, []):
            all_ids.add(item.get("id"))

    missing = REQUIRED_IDS - all_ids
    if missing:
        errors.append(f"{path.name}: Missing required IDs: {missing}")

    return errors


def validate_dates_match_filenames(path):
    """Check that the date field matches the filename."""
    errors = []
    data = load_json(path)
    expected = path.stem
    actual = data.get("date", "")
    if actual != expected:
        errors.append(f"{path.name}: date field '{actual}' != filename '{expected}'")
    return errors


def main():
    price_schema = load_schema("price_snapshot.schema.json")
    briefing_schema = load_schema("briefing.schema.json")
    news_schema = load_schema("news.schema.json")

    all_errors = []
    checked = 0

    # Validate price snapshots
    for pf in sorted(DATA_DIR.joinpath("prices").glob("*.json")):
        all_errors.extend(validate_file(pf, price_schema, "price"))
        all_errors.extend(validate_price_ids(pf))
        all_errors.extend(validate_dates_match_filenames(pf))
        checked += 1

    # Validate briefings
    for bf in sorted(DATA_DIR.joinpath("briefings").glob("*.json")):
        all_errors.extend(validate_file(bf, briefing_schema, "briefing"))
        all_errors.extend(validate_dates_match_filenames(bf))
        checked += 1

    # Validate news
    for nf in sorted(DATA_DIR.joinpath("news").glob("*.json")):
        all_errors.extend(validate_file(nf, news_schema, "news"))
        all_errors.extend(validate_dates_match_filenames(nf))
        checked += 1

    # Validate history.json exists and is valid JSON
    history_path = DATA_DIR / "history.json"
    if history_path.exists():
        try:
            load_json(history_path)
        except json.JSONDecodeError as e:
            all_errors.append(f"history.json: Invalid JSON — {e}")
        checked += 1

    # Validate latest.json
    latest_path = DATA_DIR / "latest.json"
    if latest_path.exists():
        try:
            load_json(latest_path)
        except json.JSONDecodeError as e:
            all_errors.append(f"latest.json: Invalid JSON — {e}")
        checked += 1

    if all_errors:
        print(f"VALIDATION FAILED — {len(all_errors)} error(s):\n")
        for e in all_errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"Validation passed — {checked} files checked, 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
