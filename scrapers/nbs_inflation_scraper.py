"""
NBS Inflation Scraper — fetches inflation data from NBS website with
hardcoded fallback values for recent months.

NOTE on rebasing: NBS rebased CPI in late 2025 using 2024 as the new base year
(previously 2009). This caused a sharp drop in reported YoY rates from ~33% to
~15%. The values below reflect the REBASED figures from May 2025 onward.
Pre-May 2025 values use the OLD base (2009) as originally reported by NBS.
"""
import logging
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

RECENT_CPI = {
    # ── 2024 (old base year 2009) ──
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
    # ── 2025 Jan-Apr (old base year 2009) ──
    "2025-01": {"headline": 24.48, "food": 26.08},
    "2025-02": {"headline": 23.18, "food": 24.43},
    "2025-03": {"headline": 24.23, "food": 21.79},
    "2025-04": {"headline": 23.71, "food": 21.26},
    # ── 2025 May onward (REBASED — 2024 base year) ──
    "2025-05": {"headline": 22.97, "food": 22.41},
    "2025-06": {"headline": 22.22, "food": 21.97},
    "2025-07": {"headline": 21.88, "food": 21.87},
    "2025-08": {"headline": 20.12, "food": 19.84},
    "2025-09": {"headline": 18.02, "food": 17.60},
    "2025-10": {"headline": 16.05, "food": 15.42},
    "2025-11": {"headline": 17.33, "food": 14.45},
    "2025-12": {"headline": 15.15, "food": 10.84},
    # ── 2026 (REBASED — 2024 base year) ──
    "2026-01": {"headline": 15.10, "food": 8.89},
    "2026-02": {"headline": 15.06, "food": 12.12},
    "2026-03": {"headline": 15.38, "food": 14.31},
    "2026-04": {"headline": 15.69, "food": 16.06},
    "2026-05": {"headline": 15.93, "food": 16.96},
    "2026-06": {"headline": 15.91, "food": 17.52},
}


class NBSInflationScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def fetch_latest(self) -> Optional[dict]:
        try:
            result = self._scrape_nbs()
            if result:
                return result
        except Exception as e:
            logger.warning(f"NBS scrape failed: {e}, using fallback data")
        return self._get_fallback()

    def _scrape_nbs(self) -> Optional[dict]:
        url = "https://nigerianstat.gov.ng/elibrary/read/1241460"
        with httpx.Client(timeout=20, headers=self.headers, follow_redirects=True) as client:
            r = client.get(url)

        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if any("headline" in t.lower() for t in cell_texts):
                    for i, t in enumerate(cell_texts):
                        if "headline" in t.lower() and i + 1 < len(cell_texts):
                            try:
                                headline = float(cell_texts[i + 1].replace("%", ""))
                                return {
                                    "date": date.today().replace(day=1),
                                    "headline_cpi": headline,
                                    "food_inflation": None,
                                    "source": "nbs_website",
                                }
                            except ValueError:
                                pass
        return None

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


def sync_inflation_to_db(session):
    from database.models import InflationData

    added = 0
    updated = 0
    for period, data in RECENT_CPI.items():
        year, month = period.split("-")
        d = date(int(year), int(month), 1)

        existing = session.query(InflationData).filter_by(date=d).first()
        if existing:
            if (float(existing.headline_cpi) != data["headline"]
                    or (existing.food_inflation and float(existing.food_inflation) != data["food"])):
                existing.headline_cpi = data["headline"]
                existing.food_inflation = data["food"]
                updated += 1
            continue

        record = InflationData(
            date=d,
            headline_cpi=data["headline"],
            food_inflation=data["food"],
        )
        session.add(record)
        added += 1

    session.commit()
    logger.info(f"Inflation data synced: {added} added, {updated} updated")
    return {"added": added, "updated": updated}
