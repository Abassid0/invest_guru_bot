"""
Seed approximate current NGX stock prices.
Update the prices dict below with current market data whenever needed.
Run: python seed_prices.py

Source: NGX Group daily price list (update manually from ngxgroup.com)
Last updated: June 2026
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
if sys.platform == "win32":
    import dns_patch  # noqa

from datetime import date
from decimal import Decimal
from dotenv import load_dotenv
load_dotenv()

from database.models import create_database_engine, get_session, Company, StockPrice

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
engine = create_database_engine(DATABASE_URL)
session = get_session(engine)

# ── Update these prices from ngxgroup.com/exchange/trade/equities/ ────────────
# Format: "TICKER": (close_price, volume, change_pct)
# Prices in Naira (NGN)
PRICES = {
    # Banking
    "GTCO":        (55.50,  45_000_000,  1.83),
    "ZENITHBANK":  (36.90,  38_000_000,  0.55),
    "ACCESSCORP":  (22.50,  60_000_000,  2.27),
    "UBA":         (27.80,  42_000_000,  1.46),
    "FBNH":        (28.00,  25_000_000,  0.36),
    "STANBIC":     (75.00,   8_000_000,  1.35),
    "FIDELITYBNK": (14.50,  30_000_000,  0.69),

    # Cement
    "DANGCEM":     (430.00,  5_000_000, -0.46),
    "BUACEMENT":   (115.00,  3_500_000,  0.88),
    "WAPCO":       (42.00,   2_000_000,  0.48),

    # Telecoms
    "MTNN":        (210.00,  8_000_000,  0.48),
    "AIRTELAFRI":  (2200.00,   500_000,  0.23),

    # Oil & Gas
    "SEPLAT":      (5200.00,   200_000,  0.97),
    "TOTAL":       (450.00,    400_000,  0.45),
    "CONOIL":      (120.00,    300_000,  0.84),

    # FMCG
    "NESTLE":      (1200.00,   150_000, -0.41),
    "UNILEVER":    (22.00,     800_000,  0.46),
    "FLOURMILL":   (28.00,   1_500_000,  1.82),
    "NASCON":      (52.00,     600_000,  0.97),

    # Agriculture
    "PRESCO":      (480.00,    250_000,  0.84),
    "OKOMUOIL":    (520.00,    200_000,  0.97),
}

today = date.today()
added = updated = 0
companies = {c.ticker: c for c in session.query(Company).all()}

for ticker, (close, vol, chg_pct) in PRICES.items():
    company = companies.get(ticker)
    if not company:
        print(f"  SKIP {ticker} — not in companies table")
        continue

    existing = session.query(StockPrice).filter_by(
        company_id=company.id, date=today
    ).first()

    if existing:
        existing.close = Decimal(str(close))
        existing.volume = vol
        existing.change_percent = Decimal(str(chg_pct))
        updated += 1
    else:
        session.add(StockPrice(
            company_id=company.id,
            date=today,
            close=Decimal(str(close)),
            volume=vol,
            change_percent=Decimal(str(round(chg_pct, 4))),
            source="Manual seed"
        ))
        added += 1

session.commit()
session.close()
print(f"Done — added: {added}, updated: {updated}")
print("Update prices dict from ngxgroup.com/exchange/trade/equities/ for accuracy.")
