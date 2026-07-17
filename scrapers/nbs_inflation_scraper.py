"""
Inflation Data Scraper — pulls from CBN JSON API (primary) with hardcoded
fallback values.

Primary source:  https://www.cbn.gov.ng/api/GetAllInflationRates
                 Returns JSON array sorted newest-first with fields:
                   tyear, tmonth, period, allItemsYearOn, foodYearOn
Fallback:        RECENT_CPI dict below (updated manually when CBN API is down)
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CBN_API_URL = "https://www.cbn.gov.ng/api/GetAllInflationRates"

RECENT_CPI = {
    "2024-01": {"headline": 29.90, "food": 35.41},
    "2024-02": {"headline": 31.70, "food": 37.92},
    "2024-03": {"headline": 33.20, "food": 40.01},
    "2024-04": {"headline": 33.69, "food": 40.53},
    "2024-05": {"headline": 33.95, "food": 40.66},
    "2024-06": {"headline": 34.19, "food": 40.87},
    "2024-07": {"headline": 33.40, "food": 39.53},
    "2024-08": {"headline": 32.15, "food": 37.52},
    "2024-09": {"headline": 32.70, "food": 37.77},
    "2024-10": {"headline": 33.88, "food": 39.16},
    "2024-11": {"headline": 34.60, "food": 39.93},
    "2024-12": {"headline": 34.80, "food": 39.84},
    "2025-01": {"headline": 24.48, "food": 26.08},
    "2025-02": {"headline": 23.18, "food": 24.43},
    "2025-03": {"headline": 24.23, "food": 21.79},
    "2025-04": {"headline": 23.71, "food": 21.26},
    "2025-05": {"headline": 22.97, "food": 22.41},
    "2025-06": {"headline": 22.22, "food": 21.97},
    "2025-07": {"headline": 24.94, "food": 26.20},
    "2025-08": {"headline": 23.14, "food": 25.30},
    "2025-09": {"headline": 20.98, "food": 20.16},
    "2025-10": {"headline": 18.97, "food": 16.30},
    "2025-11": {"headline": 17.33, "food": 14.21},
    "2025-12": {"headline": 15.15, "food": 10.84},
    "2026-01": {"headline": 15.10, "food": 8.89},
    "2026-02": {"headline": 15.06, "food": 12.12},
    "2026-03": {"headline": 15.38, "food": 14.31},
    "2026-04": {"headline": 15.69, "food": 16.06},
    "2026-05": {"headline": 15.93, "food": 16.96},
    "2026-06": {"headline": 15.91, "food": 17.52},
}


def _fetch_cbn_api(limit: int = 24) -> list[dict]:
    """Fetch latest inflation records from CBN JSON API.
    Returns list of dicts with keys: date, headline_cpi, food_inflation, source.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
        r = client.get(CBN_API_URL)
        r.raise_for_status()

    records = r.json()
    results = []
    for row in records[:limit]:
        try:
            year = int(row["tyear"])
            month = int(row["tmonth"])
            headline = float(row["allItemsYearOn"])
            food_raw = row.get("foodYearOn")
            food = float(food_raw) if food_raw else None
            results.append({
                "date": date(year, month, 1),
                "headline_cpi": headline,
                "food_inflation": food,
                "source": "cbn_api",
            })
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Skipping CBN row: {e}")
            continue

    return results


class NBSInflationScraper:
    def __init__(self):
        pass

    def fetch_latest(self) -> Optional[dict]:
        try:
            records = _fetch_cbn_api(limit=1)
            if records:
                logger.info(f"CBN API: latest inflation = {records[0]['headline_cpi']}%")
                return records[0]
        except Exception as e:
            logger.warning(f"CBN API failed: {e}, using fallback")

        return self._get_fallback()

    def fetch_recent(self, months: int = 24) -> list[dict]:
        try:
            records = _fetch_cbn_api(limit=months)
            if records:
                logger.info(f"CBN API: fetched {len(records)} months of inflation data")
                return records
        except Exception as e:
            logger.warning(f"CBN API failed: {e}, using fallback for all months")

        return self._get_all_fallback()

    def _get_fallback(self) -> Optional[dict]:
        if not RECENT_CPI:
            return None

        latest_key = max(RECENT_CPI.keys())
        data = RECENT_CPI[latest_key]
        year, month = latest_key.split("-")

        return {
            "date": date(int(year), int(month), 1),
            "headline_cpi": data["headline"],
            "food_inflation": data["food"],
            "source": "hardcoded_fallback",
        }

    def _get_all_fallback(self) -> list[dict]:
        results = []
        for period, data in sorted(RECENT_CPI.items(), reverse=True):
            year, month = period.split("-")
            results.append({
                "date": date(int(year), int(month), 1),
                "headline_cpi": data["headline"],
                "food_inflation": data["food"],
                "source": "hardcoded_fallback",
            })
        return results


def sync_inflation_to_db(session):
    """Sync inflation data to DB from CBN API (primary) or hardcoded fallback."""
    from database.models import InflationData

    scraper = NBSInflationScraper()
    records = scraper.fetch_recent(months=24)

    added = 0
    updated = 0
    for rec in records:
        existing = session.query(InflationData).filter_by(date=rec["date"]).first()
        if existing:
            old_headline = float(existing.headline_cpi) if existing.headline_cpi else None
            old_food = float(existing.food_inflation) if existing.food_inflation else None
            new_headline = rec["headline_cpi"]
            new_food = rec["food_inflation"]
            if old_headline != new_headline or old_food != new_food:
                existing.headline_cpi = Decimal(str(new_headline))
                if new_food is not None:
                    existing.food_inflation = Decimal(str(new_food))
                updated += 1
            continue

        record = InflationData(
            date=rec["date"],
            headline_cpi=Decimal(str(rec["headline_cpi"])),
            food_inflation=Decimal(str(rec["food_inflation"])) if rec["food_inflation"] else None,
        )
        session.add(record)
        added += 1

    session.commit()
    source = records[0]["source"] if records else "none"
    logger.info(f"Inflation sync ({source}): {added} added, {updated} updated")
    return {"added": added, "updated": updated, "source": source}
