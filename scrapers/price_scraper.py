"""
NGX Price Scraper
Fetches live stock prices from the NGX Group REST API.

Primary source:
  https://doclib.ngxgroup.com/REST/api/statistics/equities/
  Returns JSON with Symbol, OpeningPrice, HighPrice, LowPrice, ClosePrice,
  PrevClosingPrice, Change, PercChange, Volume, Trades, TradeDate, Sector.
"""
import requests
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import time
from decimal import Decimal
from loguru import logger
from retry import retry


class NGXPriceScraper:
    """
    Fetches NGX stock prices via the official REST API.
    Falls back to mock data (development only) when the API is unavailable.
    """

    # Discovered from the NGX equities price-list page JavaScript
    API_URL = (
        "https://doclib.ngxgroup.com/REST/api/statistics/equities/"
        "?market=&sector=&orderby=&pageSize=500&pageNo=0"
    )

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*",
            "Referer": "https://ngxgroup.com/exchange/data/equities-price-list/",
        })

    @retry(tries=3, delay=2, backoff=2)
    def fetch_ngx_daily_prices(self) -> List[Dict]:
        """
        Fetch today's prices for all NGX equities via the REST API.

        Returns a list of dicts with keys:
          ticker, date, open, high, low, close, change, change_percent,
          volume, trades, sector, source

        For stocks that did not trade today, ClosePrice is null in the API
        response — we use PrevClosingPrice as close and mark the source
        accordingly so callers can distinguish traded vs. non-traded records.
        """
        logger.info(f"Fetching NGX prices from API: {self.API_URL}")

        response = self.session.get(self.API_URL, timeout=20)
        response.raise_for_status()

        data = response.json()
        prices = []

        for row in data:
            try:
                ticker = (row.get("Symbol") or "").strip().upper()
                if not ticker:
                    continue

                trade_date_raw = row.get("TradeDate")
                if trade_date_raw:
                    trade_date = date.fromisoformat(trade_date_raw[:10])
                else:
                    trade_date = date.today()

                close_raw = row.get("ClosePrice")
                prev_close_raw = row.get("PrevClosingPrice")

                if close_raw is not None:
                    close = Decimal(str(close_raw))
                    source = "NGX API"
                elif prev_close_raw is not None:
                    # Stock did not trade today; carry forward previous close
                    close = Decimal(str(prev_close_raw))
                    source = "NGX API (prev close — no trade today)"
                else:
                    continue  # No price at all — skip

                def _dec(val) -> Optional[Decimal]:
                    return Decimal(str(val)) if val is not None else None

                prices.append({
                    "ticker": ticker,
                    "date": trade_date,
                    "open": _dec(row.get("OpeningPrice")),
                    "high": _dec(row.get("HighPrice")),
                    "low": _dec(row.get("LowPrice")),
                    "close": close,
                    "change": _dec(row.get("Change")),
                    "change_percent": _dec(row.get("PercChange")),
                    "volume": int(row["Volume"]) if row.get("Volume") is not None else None,
                    "trades": row.get("Trades"),
                    "sector": row.get("Sector"),
                    "source": source,
                })

            except Exception as e:
                logger.warning(f"Error parsing API row for {row.get('Symbol')}: {e}")
                continue

        logger.info(f"Fetched {len(prices)} stock prices from NGX API")
        return prices

    def fetch_historical_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """
        Historical price fetch — NGX does not expose a public historical API.
        Returns an empty DataFrame with the expected schema.
        """
        logger.warning(f"Historical data fetch not available for {ticker} — NGX API is daily only")
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume", "change", "change_percent"]
        )

    def fetch_fallback_prices(self, tickers: List[str]) -> List[Dict]:
        """
        Development-only fallback. Returns mock prices when the live API is
        unavailable. NEVER use in production — source field is clearly labelled.
        """
        logger.warning("Using fallback mock prices — NOT FOR PRODUCTION")

        import random
        mock_ranges = {
            "GTCO": (130.0, 140.0),
            "ZENITHBANK": (42.0, 48.0),
            "ACCESSCORP": (24.0, 26.0),
            "UBA": (28.0, 32.0),
            "FBNH": (30.0, 34.0),
            "STANBIC": (68.0, 75.0),
            "FIDELITYBNK": (15.0, 18.0),
            "DANGCEM": (1100.0, 1200.0),
            "BUACEMENT": (115.0, 125.0),
            "WAPCO": (40.0, 46.0),
            "MTNN": (250.0, 270.0),
            "AIRTELAFRI": (3800.0, 4200.0),
            "SEPLAT": (11000.0, 12000.0),
            "TOTAL": (500.0, 560.0),
            "CONOIL": (65.0, 72.0),
            "NESTLE": (3000.0, 3200.0),
            "UNILEVER": (20.0, 24.0),
            "FLOURMILL": (52.0, 58.0),
            "NASCON": (35.0, 40.0),
            "PRESCO": (340.0, 380.0),
            "OKOMUOIL": (220.0, 250.0),
        }

        prices = []
        for ticker in tickers:
            if ticker not in mock_ranges:
                continue
            low, high = mock_ranges[ticker]
            close_price = round(random.uniform(low, high), 2)
            change = round(random.uniform(-5.0, 5.0), 2)
            prices.append({
                "ticker": ticker,
                "date": date.today(),
                "close": close_price,
                "change": change,
                "change_percent": round((change / close_price) * 100, 2),
                "volume": random.randint(500_000, 15_000_000),
                "source": "Mock Data (Development Only)",
            })
        return prices

    def batch_fetch_prices(
        self, tickers: List[str], use_fallback: bool = True
    ) -> List[Dict]:
        """
        Fetch prices for the given tickers.

        1. Calls the NGX API (returns all equities in one request).
        2. Filters to the requested tickers.
        3. If use_fallback=True, fills any remaining gaps with mock data
           (development only — set use_fallback=False in production).
        """
        logger.info(f"Fetching prices for {len(tickers)} stocks")

        all_prices = self.fetch_ngx_daily_prices()

        # Index by ticker for fast lookup
        api_map = {p["ticker"]: p for p in all_prices}

        result = []
        missing = []

        for ticker in tickers:
            if ticker in api_map:
                result.append(api_map[ticker])
            else:
                missing.append(ticker)

        if missing:
            logger.warning(
                f"{len(missing)} tickers not found in NGX API response: {missing}"
            )

        if use_fallback and missing:
            fallback = self.fetch_fallback_prices(missing)
            result.extend(fallback)

        return result


# Standalone test
if __name__ == "__main__":
    logger.add("logs/scraper_test.log", rotation="1 day")

    scraper = NGXPriceScraper()
    test_tickers = ["GTCO", "DANGCEM", "ZENITHBANK", "MTNN", "SEPLAT", "AIRTELAFRI"]

    print("=" * 60)
    print("NGX Price Scraper Test")
    print("=" * 60)

    prices = scraper.batch_fetch_prices(test_tickers, use_fallback=False)

    print(f"\nFetched {len(prices)} prices:")
    for p in prices:
        change = p.get("change_percent") or 0
        print(
            f"  {p['ticker']:12} ₦{p['close']:>10}  "
            f"({float(change):+.2f}%)  [{p['source']}]"
        )

    print("\n" + "=" * 60)
    print("Scraper test complete")
