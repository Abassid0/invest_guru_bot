"""
Watchlist Alert Checker — queries active watches, compares against latest prices,
sends Telegram notifications for triggered alerts.
"""
import httpx

from database.models import get_session, StockPrice, Company
from database.bot_db import check_alerts, mark_alert_triggered


async def check_and_send_alerts(engine, telegram_api: str) -> int:
    session = get_session(engine)
    try:
        latest_prices = _get_latest_prices(session)
        if not latest_prices:
            return 0

        triggered = check_alerts(session, latest_prices)
        sent = 0

        for alert in triggered:
            msg = (
                f"Price Alert: {alert['ticker']}\n\n"
                f"Current price: N{alert['current_price']:,.2f}\n"
                f"Your alert: {alert['direction']} N{alert['threshold']:,.2f}\n\n"
                f"Set a new alert: /watch {alert['ticker']} PRICE"
            )
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(
                        f"{telegram_api}/sendMessage",
                        json={"chat_id": alert["telegram_id"], "text": msg},
                    )
                mark_alert_triggered(session, alert["id"])
                sent += 1
            except Exception:
                pass

        return sent
    finally:
        session.close()


def _get_latest_prices(session) -> dict:
    from sqlalchemy import func

    subq = (
        session.query(
            StockPrice.company_id,
            func.max(StockPrice.date).label("max_date"),
        )
        .group_by(StockPrice.company_id)
        .subquery()
    )

    rows = (
        session.query(Company.ticker, StockPrice.close_price)
        .join(StockPrice, Company.id == StockPrice.company_id)
        .join(
            subq,
            (StockPrice.company_id == subq.c.company_id)
            & (StockPrice.date == subq.c.max_date),
        )
        .all()
    )

    return {ticker: float(price) for ticker, price in rows if price}
