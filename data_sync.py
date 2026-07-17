"""
NGX Real-Time Data Sync
Fetches live stock prices, FX rates, and commodity prices then stores in Supabase.

Run manually:   python data_sync.py
Run via API:    POST /api/sync?admin_key=X  (from Railway scheduler or cron)

Data sources:
  - Stock prices  : NGX Group website scraping (ngxgroup.com)
  - FX rates      : ExchangeRate-API (free, no key needed)
  - Brent crude   : Yahoo Finance (BZ=F — works fine)

NOTE: Claude's web_search tool in the Telegram bot ALSO provides real-time
data on every query — the DB sync is a secondary layer for REST API endpoints.
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




def _fetch_ngx_prices() -> dict:
    """
    Fetch NGX daily closing prices via the official REST API.
    Returns {ticker: {"close": float, "volume": int, "change_pct": float}}
    """
    from scrapers.price_scraper import NGXPriceScraper

    scraper = NGXPriceScraper()
    prices_list = scraper.fetch_ngx_daily_prices()

    return {
        p["ticker"]: {
            "close": float(p["close"]),
            "volume": p.get("volume") or 0,
            "change_pct": float(p.get("change_percent") or 0),
        }
        for p in prices_list
    }


YAHOO_TICKER_MAP = {
    "GTCO": "GUARANTY.LG",
    "ZENITHBANK": "ZENITHBANK.LG",
    "ACCESSCORP": "ACCESSCORP.LG",
    "UBA": "UBA.LG",
    "FIRSTHOLDCO": "FIRSTHOLDCO.LG",
    "STANBIC": "STANBIC.LG",
    "FIDELITYBK": "FIDELITYBK.LG",
    "DANGCEM": "DANGCEM.LG",
    "BUACEMENT": "BUACEMENT.LG",
    "MTNN": "MTNN.LG",
    "AIRTELAFRI": "AIRTELAFRI.LG",
    "SEPLAT": "SEPLAT.LG",
    "TOTAL": "TOTAL.LG",
    "CONOIL": "CONOIL.LG",
    "NESTLE": "NESTLE.LG",
    "UNILEVER": "UNILEVER.LG",
    "NNFM": "NNFM.LG",
    "NASCON": "NASCON.LG",
    "PRESCO": "PRESCO.LG",
    "OKOMUOIL": "OKOMUOIL.LG",
}


def _fetch_yahoo_prices(tickers: list) -> dict:
    """Fallback: fetch prices from Yahoo Finance for tickers missing from NGX API."""
    import yfinance as yf

    result = {}
    for ticker in tickers:
        yahoo_sym = YAHOO_TICKER_MAP.get(ticker, f"{ticker}.LG")
        try:
            data = yf.download(yahoo_sym, period="2d", interval="1d", progress=False, auto_adjust=True)
            if data.empty:
                continue
            raw = data["Close"].values[-1]
            close = float(raw) if not hasattr(raw, "__len__") else float(raw.flat[0])
            result[ticker] = {"close": close, "volume": 0, "change_pct": 0.0}
        except Exception:
            continue
    return result


def sync_stock_prices() -> dict:
    """Fetch NGX prices, fill gaps with Yahoo Finance, upsert to DB."""
    raw = _fetch_ngx_prices()
    if not raw:
        return {"error": "NGX scrape returned no data -- site may be unreachable or layout changed"}

    session = get_session(engine)
    today = date.today()
    added = 0
    updated = 0
    not_in_db = []
    yahoo_filled = []

    companies = session.query(Company).filter_by(is_active=True).all()
    company_map = {c.ticker: c for c in companies}

    # Find DB stocks missing from NGX API
    missing_from_api = [t for t in company_map if t not in raw]
    if missing_from_api:
        yahoo_prices = _fetch_yahoo_prices(missing_from_api)
        raw.update(yahoo_prices)
        yahoo_filled = list(yahoo_prices.keys())

    for ticker, data in raw.items():
        company = company_map.get(ticker)
        if not company:
            not_in_db.append(ticker)
            continue

        close_price = data["close"]
        volume = data["volume"]
        change_pct = data["change_pct"]
        source = "Yahoo Finance" if ticker in yahoo_filled else "NGX Group"

        existing = session.query(StockPrice).filter_by(
            company_id=company.id, date=today
        ).first()

        if existing:
            existing.close = Decimal(str(round(close_price, 2)))
            existing.volume = volume
            existing.change_percent = Decimal(str(round(change_pct, 4)))
            updated += 1
        else:
            session.add(StockPrice(
                company_id=company.id,
                date=today,
                close=Decimal(str(round(close_price, 2))),
                volume=volume,
                change_percent=Decimal(str(round(change_pct, 4))),
                source=source
            ))
            added += 1

    session.commit()
    session.close()
    return {
        "added": added,
        "updated": updated,
        "ngx_tickers_scraped": len(raw),
        "yahoo_fallback": yahoo_filled,
        "not_in_db": not_in_db[:10],
    }


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
        import yfinance as yf
        brent = yf.download("BZ=F", period="2d", interval="1d", progress=False, auto_adjust=True)
        if brent.empty:
            return {"error": "Brent data unavailable"}

        # yfinance may return a Series or scalar — use .values to get numpy scalar
        raw = brent["Close"].values[-1]
        price = float(raw) if not hasattr(raw, "__len__") else float(raw.flat[0])

        session = get_session(engine)
        latest = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        if latest:
            latest.brent_crude_usd = Decimal(str(round(price, 2)))
            session.commit()
        session.close()
        return {"brent_usd": round(price, 2)}
    except Exception as e:
        return {"error": str(e)}


def run_full_sync() -> dict:
    """Run all sync tasks and return a summary."""
    from database.bot_db import expire_old_conversations, log_sync

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

    # Sync inflation data
    print("  Syncing inflation data...")
    try:
        from scrapers.nbs_inflation_scraper import sync_inflation_to_db
        session = get_session(engine)
        inflation_result = sync_inflation_to_db(session)
        session.close()
        result["inflation"] = inflation_result
        print(f"  Inflation: {inflation_result}")
    except Exception as e:
        result["inflation"] = f"error: {e}"
        print(f"  Inflation sync warning: {e}")

    # Recalculate inflation performance
    print("  Recalculating inflation performance...")
    try:
        from calculators.inflation_calculator import InflationCalculator
        calc = InflationCalculator(DATABASE_URL)
        perf_results = calc.batch_calculate_performance()
        success = sum(1 for v in perf_results.values() if v)
        result["performance_recalc"] = f"{success}/{len(perf_results)}"
        print(f"  Performance: {success}/{len(perf_results)} stocks updated")
        calc.close()
    except Exception as e:
        result["performance_recalc"] = f"error: {e}"
        print(f"  Performance recalc warning: {e}")

    # Housekeeping
    print("  Cleaning old conversations...")
    session = get_session(engine)
    try:
        deleted = expire_old_conversations(session, hours=24)
        result["conversations_cleaned"] = deleted
        print(f"  Removed {deleted} old conversation rows")

        stocks_result = result.get("stocks", {})
        log_sync(session, "full_sync", "success",
                 records_affected=stocks_result.get("added", 0) + stocks_result.get("updated", 0))
    except Exception as e:
        print(f"  Housekeeping warning: {e}")
    finally:
        session.close()

    print(f"[{datetime.now().isoformat()}] Sync complete.")
    return result


if __name__ == "__main__":
    result = run_full_sync()
    import json
    print("\n=== SYNC RESULT ===")
    print(json.dumps(result, indent=2, default=str))
