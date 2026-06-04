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




def _scrape_ngx_prices() -> dict:
    """
    Scrape latest stock prices from the NGX Group equities page.
    Returns {ticker: {"close": float, "volume": int, "change_pct": float}}
    """
    from bs4 import BeautifulSoup

    url = "https://ngxgroup.com/exchange/trade/equities/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NGXBot/1.0)"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    prices = {}

    # NGX table has columns: Symbol | Open | High | Low | Close | Change | %Change | Volume | Value | Trades
    for row in soup.select("table tbody tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 7:
            continue
        try:
            ticker = cols[0].upper().replace(" ", "")
            close = float(cols[4].replace(",", ""))
            change_str = cols[6].replace("%", "").replace(",", "").strip()
            change_pct = float(change_str) if change_str not in ("", "-", "N/A") else 0.0
            vol_str = cols[7].replace(",", "") if len(cols) > 7 else "0"
            volume = int(float(vol_str)) if vol_str.replace(".", "").isdigit() else 0
            prices[ticker] = {"close": close, "volume": volume, "change_pct": change_pct}
        except (ValueError, IndexError):
            continue

    return prices


def sync_stock_prices() -> dict:
    """Scrape NGX Group website for today's prices and upsert to DB."""
    raw = _scrape_ngx_prices()
    if not raw:
        return {"error": "NGX scrape returned no data — site may be unreachable or layout changed"}

    session = get_session(engine)
    today = date.today()
    added = 0
    updated = 0
    not_in_db = []

    companies = session.query(Company).filter_by(is_active=True).all()
    company_map = {c.ticker: c for c in companies}

    for ticker, data in raw.items():
        company = company_map.get(ticker)
        if not company:
            not_in_db.append(ticker)
            continue

        close_price = data["close"]
        volume = data["volume"]
        change_pct = data["change_pct"]

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
                source="NGX Group"
            ))
            added += 1

    session.commit()
    session.close()
    return {
        "added": added,
        "updated": updated,
        "ngx_tickers_scraped": len(raw),
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
