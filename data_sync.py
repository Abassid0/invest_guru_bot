"""
NGX Real-Time Data Sync
Fetches live stock prices, FX rates, and T-bill rates then stores in Supabase.

Run manually:   python data_sync.py
Run via API:    POST /api/sync  (from Railway scheduler or cron)

Data sources:
  - Stock prices  : Yahoo Finance (yfinance) — NGX tickers with .LG suffix
  - FX rates      : ExchangeRate-API (free tier, no key needed for NGN)
  - T-bill rates  : CBN/DMO latest auction data (seeded manually when updated)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
if sys.platform == "win32":
    import dns_patch  # noqa: F401  — local DNS workaround

from datetime import date, datetime
from decimal import Decimal
import requests
from dotenv import load_dotenv

load_dotenv()

from database.models import (
    create_database_engine, get_session,
    Company, StockPrice, MacroIndicator, InflationData
)

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set")

engine = create_database_engine(DATABASE_URL)


# ── NGX ticker map: DB ticker → Yahoo Finance symbol ─────────────────────────
# Yahoo Finance uses .LG (Lagos) suffix for NGX-listed stocks
NGX_YAHOO_MAP = {
    "GTCO":        "GTCO.LG",
    "ZENITHBANK":  "ZENITHBA.LG",
    "ACCESSCORP":  "ACCESSCO.LG",
    "UBA":         "UBA.LG",
    "FBNH":        "FBNH.LG",
    "STANBIC":     "STANBIC.LG",
    "FIDELITYBNK": "FIDELITY.LG",
    "DANGCEM":     "DANGCEM.LG",
    "BUACEMENT":   "BUACEM.LG",
    "WAPCO":       "WAPCO.LG",
    "MTNN":        "MTNN.LG",
    "AIRTELAFRI":  "AIRTELAF.LG",
    "SEPLAT":      "SEPL.LG",
    "TOTAL":       "TOTAL.LG",
    "NESTLE":      "NESTLE.LG",
    "UNILEVER":    "UNILEVE.LG",
    "FLOURMILL":   "FLOURMI.LG",
    "PRESCO":      "PRESCO.LG",
    "OKOMUOIL":    "OKOMUOI.LG",
}


def sync_stock_prices() -> dict:
    """Fetch today's closing prices from Yahoo Finance and upsert to DB."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed — run: pip install yfinance"}

    session = get_session(engine)
    today = date.today()
    added = 0
    updated = 0
    failed = []

    companies = session.query(Company).filter_by(is_active=True).all()
    company_map = {c.ticker: c for c in companies}

    for ticker, yahoo_sym in NGX_YAHOO_MAP.items():
        company = company_map.get(ticker)
        if not company:
            continue
        try:
            data = yf.download(yahoo_sym, period="5d", interval="1d", progress=False, auto_adjust=True)
            if data.empty:
                failed.append(f"{ticker} (no data)")
                continue

            latest = data.iloc[-1]
            close_price = float(latest["Close"].iloc[0] if hasattr(latest["Close"], "iloc") else latest["Close"])
            volume = int(latest["Volume"].iloc[0] if hasattr(latest["Volume"], "iloc") else latest["Volume"])
            price_date = data.index[-1].date()

            # Check previous close for change %
            if len(data) >= 2:
                prev_close = float(data.iloc[-2]["Close"].iloc[0] if hasattr(data.iloc[-2]["Close"], "iloc") else data.iloc[-2]["Close"])
                change = close_price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = 0
                change_pct = 0

            # Upsert
            existing = session.query(StockPrice).filter_by(
                company_id=company.id, date=price_date
            ).first()

            if existing:
                existing.close = Decimal(str(round(close_price, 2)))
                existing.volume = volume
                existing.change = Decimal(str(round(change, 2)))
                existing.change_percent = Decimal(str(round(change_pct, 4)))
                updated += 1
            else:
                session.add(StockPrice(
                    company_id=company.id,
                    date=price_date,
                    close=Decimal(str(round(close_price, 2))),
                    volume=volume,
                    change=Decimal(str(round(change, 2))),
                    change_percent=Decimal(str(round(change_pct, 4))),
                    source="Yahoo Finance"
                ))
                added += 1

        except Exception as e:
            failed.append(f"{ticker}: {str(e)[:80]}")

    session.commit()
    session.close()
    return {"added": added, "updated": updated, "failed": failed}


def sync_fx_rates() -> dict:
    """Fetch latest USD/NGN rate and update most recent MacroIndicator row."""
    try:
        # Free endpoint — no API key needed
        r = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=10
        )
        data = r.json()
        if not data.get("result") == "success":
            return {"error": "ExchangeRate API failed", "detail": data}

        ngn_rate = data["rates"].get("NGN")
        if not ngn_rate:
            return {"error": "NGN rate not in response"}

        session = get_session(engine)
        latest = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        today = date.today()

        if latest and latest.date == today:
            latest.usd_ngn_official = Decimal(str(round(ngn_rate, 2)))
        elif latest:
            # Add today's row copying most recent MPR/T-bill data
            session.add(MacroIndicator(
                date=today,
                mpr=latest.mpr,
                crar=latest.crar,
                liquidity_ratio=latest.liquidity_ratio,
                usd_ngn_official=Decimal(str(round(ngn_rate, 2))),
                usd_ngn_parallel=Decimal(str(round(ngn_rate * 1.03, 2))),  # ~3% parallel premium
                treasury_bill_91d=latest.treasury_bill_91d,
                treasury_bill_182d=latest.treasury_bill_182d,
                treasury_bill_364d=latest.treasury_bill_364d,
                brent_crude_usd=latest.brent_crude_usd,
                source="ExchangeRate-API + CBN"
            ))

        session.commit()
        session.close()
        return {"usd_ngn": ngn_rate, "date": today.isoformat()}

    except Exception as e:
        return {"error": str(e)}


def sync_brent_crude() -> dict:
    """Fetch Brent crude price and update MacroIndicator."""
    try:
        # Yahoo Finance for Brent crude
        import yfinance as yf
        brent = yf.download("BZ=F", period="2d", interval="1d", progress=False, auto_adjust=True)
        if brent.empty:
            return {"error": "Brent data unavailable"}

        price = float(brent["Close"].iloc[-1])
        session = get_session(engine)
        latest = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        if latest:
            latest.brent_crude_usd = Decimal(str(round(price, 2)))
            session.commit()
        session.close()
        return {"brent_usd": price}
    except Exception as e:
        return {"error": str(e)}


def run_full_sync() -> dict:
    """Run all sync tasks and return a summary."""
    print(f"[{datetime.now().isoformat()}] Starting full data sync...")
    result = {}

    print("  Syncing stock prices...")
    result["stocks"] = sync_stock_prices()
    print(f"  Done: {result['stocks']}")

    print("  Syncing FX rates...")
    result["fx"] = sync_fx_rates()
    print(f"  Done: {result['fx']}")

    print("  Syncing Brent crude...")
    result["brent"] = sync_brent_crude()
    print(f"  Done: {result['brent']}")

    print(f"[{datetime.now().isoformat()}] Sync complete.")
    return result


if __name__ == "__main__":
    result = run_full_sync()
    import json
    print("\n=== SYNC RESULT ===")
    print(json.dumps(result, indent=2, default=str))
