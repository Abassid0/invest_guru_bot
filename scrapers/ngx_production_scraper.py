"""
NGX Production Scraper — 3 fallback sources for stock prices.
Sources: NGX Group website, Yahoo Finance, Investing.com
"""
import logging
import time
from datetime import datetime, date
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

YAHOO_TICKER_MAP = {
    "GTCO": "GTCO.LG", "ZENITHBANK": "ZENITHBA.LG", "ACCESSCORP": "ACCESSCO.LG",
    "UBA": "UBA.LG", "FBNH": "FBNH.LG", "STANBIC": "STANBIC.LG",
    "FCMB": "FCMB.LG", "STERLINGNG": "STERLING.LG", "WEMABANK": "WEMABANK.LG",
    "DANGCEM": "DANGCEM.LG", "BUACEMENT": "BUACEMEN.LG", "WAPCO": "WAPCO.LG",
    "SEPLAT": "SEPLAT.LG", "OANDO": "OANDO.LG", "MTNN": "MTNN.LG",
    "AIRTELAFRI": "AIRTELA.LG", "DANGSUGAR": "DANGSUGAR.LG", "FLOURMILL": "FLOURMIL.LG",
    "NESTLE": "NESTLE.LG", "PRESCO": "PRESCO.LG", "TRANSCORP": "TRANSCOR.LG",
    "GEREGU": "GEREGU.LG", "GUINNESS": "GUINNESS.LG", "NB": "NB.LG",
    "CADBURY": "CADBURY.LG", "PZ": "PZ.LG", "BUAFOODS": "BUAFOODS.LG",
    "CONOIL": "CONOIL.LG", "TOTALENERG": "TOTALEN.LG", "ARDOVA": "ARDOVA.LG",
    "NEM": "NEM.LG", "MANSARD": "MANSARD.LG", "CUSTODIAN": "CUSTODIAN.LG",
    "AIICO": "AIICO.LG", "FIDSON": "FIDSON.LG", "VITAFOAM": "VITAFOAM.LG",
    "OKOMUOIL": "OKOMUOIL.LG", "INTBREW": "INTBREW.LG",
}


class NGXProductionScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.rate_limit_delay = 2.0

    def batch_fetch_prices(self, tickers: list[str]) -> dict:
        results = {}
        for ticker in tickers:
            price = self._fetch_price(ticker)
            if price:
                results[ticker] = price
            time.sleep(self.rate_limit_delay)
        logger.info(f"Fetched prices for {len(results)}/{len(tickers)} stocks")
        return results

    def _fetch_price(self, ticker: str) -> Optional[dict]:
        for source_fn in [self._from_yahoo, self._from_ngx]:
            try:
                result = source_fn(ticker)
                if result and result.get("close"):
                    result["source"] = source_fn.__name__
                    return result
            except Exception as e:
                logger.warning(f"{source_fn.__name__} failed for {ticker}: {e}")
        return None

    def _from_yahoo(self, ticker: str) -> Optional[dict]:
        yahoo_ticker = YAHOO_TICKER_MAP.get(ticker)
        if not yahoo_ticker:
            return None

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        params = {"range": "1d", "interval": "1d"}

        with httpx.Client(timeout=15, headers=self.headers) as client:
            r = client.get(url, params=params)
            if r.status_code != 200:
                return None

        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]

        close_prices = quote.get("close", [])
        open_prices = quote.get("open", [])
        high_prices = quote.get("high", [])
        low_prices = quote.get("low", [])
        volumes = quote.get("volume", [])

        if not close_prices or close_prices[-1] is None:
            return None

        return {
            "ticker": ticker,
            "date": date.today(),
            "open": open_prices[-1] if open_prices else None,
            "high": high_prices[-1] if high_prices else None,
            "low": low_prices[-1] if low_prices else None,
            "close": close_prices[-1],
            "volume": volumes[-1] if volumes else None,
            "prev_close": meta.get("previousClose"),
        }

    def _from_ngx(self, ticker: str) -> Optional[dict]:
        url = f"https://ngxgroup.com/exchange/data/company-profile/{ticker}.html"
        try:
            with httpx.Client(timeout=15, headers=self.headers, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code != 200:
                    return None

            soup = BeautifulSoup(r.text, "html.parser")
            price_elem = soup.select_one(".price-value, .current-price, [data-price]")
            if not price_elem:
                return None

            price_text = price_elem.get_text(strip=True)
            price = float(price_text.replace(",", "").replace("₦", ""))

            return {
                "ticker": ticker,
                "date": date.today(),
                "close": price,
                "open": None,
                "high": None,
                "low": None,
                "volume": None,
            }
        except (ValueError, AttributeError):
            return None
