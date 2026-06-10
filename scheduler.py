"""
NGX Daily Data Scheduler
Fetches stock prices every weekday after NGX market close (3:00 PM WAT)
and recalculates inflation performance metrics.

Schedule (UTC times, server must run in UTC):
  14:30 UTC = 3:30 PM WAT  — daily price update
  15:00 UTC = 4:00 PM WAT  — performance recalculation
"""
import os
import sys
import time
import signal
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

import schedule
from dotenv import load_dotenv
from loguru import logger

sys.path.append(os.path.dirname(__file__))

from database.models import (
    create_database_engine, get_session,
    Company, StockPrice
)
from scrapers.price_scraper import NGXPriceScraper
from calculators.inflation_calculator import InflationCalculator

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ngx_user:ngx_password@localhost:5432/ngx_data"
)

logger.add(
    "logs/scheduler_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def save_prices_to_db(session, prices: list) -> tuple[int, int]:
    """
    Upsert fetched price dicts into stock_prices table.
    Returns (inserted, updated) counts.
    Skips mock/generated data — production only saves real scrapes.
    """
    inserted = updated = 0

    for price_data in prices:
        ticker = price_data.get("ticker")
        if not ticker:
            continue

        source = price_data.get("source", "")
        if "Mock" in source or "Generated" in source:
            logger.warning(f"Skipping non-live data for {ticker} (source: {source})")
            continue

        company = session.query(Company).filter_by(ticker=ticker).first()
        if not company:
            logger.warning(f"Unknown ticker {ticker} — not in companies table, skipping")
            continue

        price_date = price_data.get("date", date.today())
        close = price_data.get("close")
        if close is None:
            logger.warning(f"No close price for {ticker}, skipping")
            continue

        existing = session.query(StockPrice).filter_by(
            company_id=company.id,
            date=price_date
        ).first()

        if existing:
            existing.close = _to_decimal(close)
            existing.change = _to_decimal(price_data.get("change", 0))
            if price_data.get("change_percent") is not None:
                existing.change_percent = _to_decimal(price_data["change_percent"])
            if price_data.get("volume") is not None:
                existing.volume = price_data["volume"]
            existing.source = source
            updated += 1
        else:
            record = StockPrice(
                company_id=company.id,
                date=price_date,
                close=_to_decimal(close),
                change=_to_decimal(price_data.get("change", 0)),
                change_percent=_to_decimal(price_data["change_percent"]) if price_data.get("change_percent") is not None else None,
                volume=price_data.get("volume"),
                source=source,
            )
            session.add(record)
            inserted += 1

    session.commit()
    return inserted, updated


def run_daily_price_update():
    """Fetch today's prices from NGX and save to database."""
    if date.today().weekday() >= 5:
        logger.info("Weekend — skipping price update")
        return

    logger.info("=" * 55)
    logger.info(f"Daily price update started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    engine = create_database_engine(DATABASE_URL)
    session = get_session(engine)

    try:
        companies = session.query(Company).filter_by(is_active=True).all()
        tickers = [c.ticker for c in companies]
        logger.info(f"Fetching prices for {len(tickers)} stocks")

        scraper = NGXPriceScraper()
        # use_fallback=False: never save mock data to production DB
        prices = scraper.batch_fetch_prices(tickers, use_fallback=False)

        if not prices:
            logger.error(
                "NGX scraper returned 0 prices. "
                "The website HTML structure may have changed — check price_scraper.py selectors."
            )
            return

        inserted, updated = save_prices_to_db(session, prices)
        logger.info(
            f"Price update complete — fetched: {len(prices)}, "
            f"inserted: {inserted}, updated: {updated}"
        )

    except Exception as e:
        logger.error(f"Price update failed: {e}")
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def run_performance_recalculation():
    """Recalculate inflation-beating performance metrics after prices are updated."""
    if date.today().weekday() >= 5:
        return

    logger.info("Recalculating inflation performance metrics...")

    try:
        calculator = InflationCalculator(DATABASE_URL)
        results = calculator.batch_calculate_performance()
        successful = sum(1 for v in results.values() if v)
        logger.info(f"Performance recalculation done — {successful}/{len(results)} stocks updated")
        calculator.close()
    except Exception as e:
        logger.error(f"Performance recalculation failed: {e}")


def setup_schedule():
    """Register all daily jobs."""
    # NGX market closes at 3:00 PM WAT (UTC+1).
    # Server must run in UTC for these times to be correct.
    schedule.every().day.at("14:30").do(run_daily_price_update)       # 3:30 PM WAT
    schedule.every().day.at("15:00").do(run_performance_recalculation) # 4:00 PM WAT

    logger.info("Scheduler registered:")
    logger.info("  14:30 UTC (3:30 PM WAT) — daily price update")
    logger.info("  15:00 UTC (4:00 PM WAT) — performance recalculation")


def handle_shutdown(signum, frame):
    logger.info("Scheduler received shutdown signal, exiting.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("NGX Data Scheduler starting...")
    setup_schedule()

    # Run once immediately on first start so today's data is not missed
    # if the container starts after market close.
    logger.info("Running initial price update on startup...")
    run_daily_price_update()
    run_performance_recalculation()

    logger.info("Entering scheduler loop (checking every 60 seconds)...")
    while True:
        schedule.run_pending()
        time.sleep(60)
