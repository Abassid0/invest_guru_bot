"""
NGX Backtesting Engine
Test inflation-beating strategy against historical data
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd
from decimal import Decimal

from database.models import (
    create_database_engine, get_session,
    Company, StockPrice, InflationPerformance, InflationData
)
from sqlalchemy import and_, func


class BacktestResult:
    """Holds backtest results"""
    def __init__(self):
        self.total_return = 0.0
        self.annual_return = 0.0
        self.sharpe_ratio = 0.0
        self.max_drawdown = 0.0
        self.win_rate = 0.0
        self.num_trades = 0
        self.avg_trade_return = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.profit_factor = 0.0
        self.strategy_trades = []
        self.portfolio_value_over_time = []
        self.dates = []


class NGXBacktestEngine:
    """Backtest NGX inflation-beating strategy"""

    def __init__(self, database_url: str):
        self.engine = create_database_engine(database_url)
        self.session = None

    def backtest_inflation_strategy(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 1_000_000,
        portfolio_size: int = 10,
        rebalance_frequency: str = "quarterly",
        min_excess_return_threshold: float = 5.0,
        strategy_name: str = "Inflation Beater"
    ) -> Dict:
        """
        Backtest the inflation-beating strategy

        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting amount in naira
            portfolio_size: Number of stocks to hold
            rebalance_frequency: How often to rebalance portfolio
            min_excess_return_threshold: Minimum excess return threshold
            strategy_name: Name of strategy

        Returns:
            Dictionary with backtest results
        """
        self.session = get_session(self.engine)

        try:
            price_data = self._get_price_data(start_date, end_date)

            if price_data.empty:
                return {"error": "No price data available for period"}

            portfolio_values, trades, dates = self._simulate_portfolio(
                price_data,
                start_date,
                end_date,
                initial_capital,
                portfolio_size,
                rebalance_frequency,
                min_excess_return_threshold
            )

            metrics = self._calculate_metrics(
                portfolio_values,
                trades,
                initial_capital,
                start_date,
                end_date
            )

            return {
                "status": "success",
                "strategy_name": strategy_name,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": (end_date - start_date).days
                },
                "parameters": {
                    "initial_capital": initial_capital,
                    "portfolio_size": portfolio_size,
                    "rebalance_frequency": rebalance_frequency,
                    "min_excess_return": min_excess_return_threshold
                },
                "metrics": metrics,
                "portfolio_values": portfolio_values,
                "trades": trades,
                "dates": dates
            }

        finally:
            self.session.close()

    def backtest_buy_and_hold(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 1_000_000,
        equal_weight: bool = True
    ) -> Dict:
        """
        Backtest simple buy-and-hold strategy

        Args:
            tickers: List of stock tickers
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital
            equal_weight: Whether to use equal weights

        Returns:
            Backtest results
        """
        self.session = get_session(self.engine)

        try:
            price_data = self._get_price_data(start_date, end_date)
            price_data = price_data[price_data['ticker'].isin(tickers)]

            if price_data.empty:
                return {"error": "No data for selected tickers"}

            weights = {ticker: 1 / len(tickers) for ticker in tickers}

            portfolio_values, trades, dates = self._simulate_buy_and_hold(
                price_data,
                start_date,
                end_date,
                initial_capital,
                weights
            )

            metrics = self._calculate_metrics(
                portfolio_values,
                trades,
                initial_capital,
                start_date,
                end_date
            )

            return {
                "status": "success",
                "strategy_name": "Buy & Hold",
                "tickers": tickers,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": (end_date - start_date).days
                },
                "metrics": metrics,
                "portfolio_values": portfolio_values,
                "trades": trades,
                "dates": dates
            }

        finally:
            self.session.close()

    def compare_strategies(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 1_000_000
    ) -> Dict:
        """
        Compare inflation-beating strategy vs buy-and-hold vs benchmarks

        Returns:
            Comparison results dict
        """
        results = {}

        results["inflation_beater"] = self.backtest_inflation_strategy(
            start_date, end_date, initial_capital
        )

        self.session = get_session(self.engine)
        try:
            top_performers = self.session.query(Company.ticker).join(
                InflationPerformance
            ).filter(
                InflationPerformance.excess_return_3yr > 0
            ).order_by(
                InflationPerformance.excess_return_3yr.desc()
            ).limit(10).all()

            tickers = [t[0] for t in top_performers]

            if tickers:
                results["top_10_performers"] = self.backtest_buy_and_hold(
                    tickers, start_date, end_date, initial_capital
                )
        finally:
            self.session.close()

        results["comparison_summary"] = self._compare_results(results)

        return results

    def backtest_devaluation_strategy(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 1_000_000,
        portfolio_size: int = 10,
        rebalance_frequency: str = "quarterly",
    ) -> Dict:
        """
        Backtest FX Revenue Filter strategy — invest in companies that earn
        foreign currency (natural naira hedge). Scores stocks by:
        - has_fx_revenue flag (weight 3)
        - Sector is Oil & Gas / Telecoms / Agriculture (weight 1)
        Rebalances into top-N scored stocks.
        """
        self.session = get_session(self.engine)

        try:
            price_data = self._get_price_data(start_date, end_date)
            if price_data.empty:
                return {"error": "No price data available for period"}

            fx_tickers = self._get_fx_revenue_stocks()
            if not fx_tickers:
                return {"error": "No FX-revenue stocks found in database"}

            selected_tickers = fx_tickers[:portfolio_size]
            weights = {t: 1 / len(selected_tickers) for t in selected_tickers}

            filtered_data = price_data[price_data["ticker"].isin(selected_tickers)]
            if filtered_data.empty:
                return {"error": "No price data for FX-revenue stocks"}

            portfolio_values, trades, dates = self._simulate_buy_and_hold(
                filtered_data, start_date, end_date, initial_capital, weights
            )

            metrics = self._calculate_metrics(
                portfolio_values, trades, initial_capital, start_date, end_date
            )

            return {
                "status": "success",
                "strategy_name": "FX Revenue Filter (Naira Hedge)",
                "tickers": selected_tickers,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": (end_date - start_date).days,
                },
                "metrics": metrics,
                "portfolio_values": portfolio_values,
                "trades": trades,
                "dates": dates,
            }
        finally:
            self.session.close()

    def _get_fx_revenue_stocks(self) -> List[str]:
        """Return tickers scored by FX revenue exposure, highest first."""
        FX_SECTORS = {"Oil & Gas", "Telecoms", "Agriculture"}

        companies = self.session.query(Company).filter_by(is_active=True).all()
        scored = []
        for c in companies:
            score = 0
            if c.has_fx_revenue:
                score += 3
            if c.sector in FX_SECTORS:
                score += 1
            if score > 0:
                scored.append((c.ticker, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in scored]

    # ==================== PRIVATE METHODS ====================

    def _get_price_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Get price data from database"""
        stocks = self.session.query(
            StockPrice.company_id,
            StockPrice.date,
            StockPrice.close,
            StockPrice.volume,
            Company.ticker
        ).join(Company).filter(
            and_(
                StockPrice.date >= start_date,
                StockPrice.date <= end_date,
                Company.is_active == True
            )
        ).all()

        if not stocks:
            return pd.DataFrame()

        df = pd.DataFrame([
            {
                'company_id': s[0],
                'date': s[1],
                'close': float(s[2]),
                'volume': int(s[3] or 0),
                'ticker': s[4]
            }
            for s in stocks
        ])

        return df.sort_values('date')

    def _simulate_portfolio(
        self,
        price_data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        portfolio_size: int,
        rebalance_frequency: str,
        min_excess_return: float
    ) -> Tuple[List[float], List[Dict], List[str]]:
        """Simulate portfolio performance"""
        portfolio_value = initial_capital
        portfolio_values = [initial_capital]
        trades = []
        dates = []

        dates_unique = sorted(price_data['date'].unique())
        current_holdings = {}
        last_rebalance = start_date

        for date in dates_unique:
            date_str = pd.Timestamp(date).to_pydatetime() if not isinstance(date, datetime) else date

            if self._should_rebalance(last_rebalance, date_str, rebalance_frequency):
                beaters = self._get_inflation_beaters_at_date(date_str, min_excess_return)
                selected = beaters[:portfolio_size]

                if selected:
                    for ticker, shares in current_holdings.items():
                        price = self._get_price_at_date(price_data, ticker, date_str)
                        if price:
                            portfolio_value += shares * price
                            trades.append({
                                "date": date_str.isoformat(),
                                "ticker": ticker,
                                "action": "SELL",
                                "shares": shares,
                                "price": price,
                                "value": shares * price
                            })

                    allocation = portfolio_value / len(selected)
                    current_holdings = {}

                    for ticker_dict in selected:
                        ticker = ticker_dict['ticker']
                        price = self._get_price_at_date(price_data, ticker, date_str)

                        if price:
                            shares = int(allocation / price)
                            if shares > 0:
                                current_holdings[ticker] = shares
                                trades.append({
                                    "date": date_str.isoformat(),
                                    "ticker": ticker,
                                    "action": "BUY",
                                    "shares": shares,
                                    "price": price,
                                    "value": shares * price
                                })

                    last_rebalance = date_str

            day_value = 0
            for ticker, shares in current_holdings.items():
                price = self._get_price_at_date(price_data, ticker, date_str)
                if price:
                    day_value += shares * price

            portfolio_value = day_value if day_value > 0 else portfolio_value
            portfolio_values.append(portfolio_value)
            dates.append(date_str.isoformat())

        return portfolio_values, trades, dates

    def _simulate_buy_and_hold(
        self,
        price_data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        weights: Dict
    ) -> Tuple[List[float], List[Dict], List[str]]:
        """Simulate buy and hold strategy"""
        portfolio_values = [initial_capital]
        trades = []
        dates = []

        shares_held = {}
        dates_unique = sorted(price_data['date'].unique())

        if not dates_unique:
            return portfolio_values, trades, dates

        first_date = dates_unique[0]

        for ticker, weight in weights.items():
            allocation = initial_capital * weight
            price = self._get_price_at_date(price_data, ticker, first_date)

            if price:
                shares = int(allocation / price)
                shares_held[ticker] = shares
                trades.append({
                    "date": first_date.isoformat() if isinstance(first_date, datetime) else str(first_date),
                    "ticker": ticker,
                    "action": "BUY",
                    "shares": shares,
                    "price": price,
                    "value": shares * price
                })

        for date in dates_unique:
            portfolio_value = 0
            for ticker, shares in shares_held.items():
                price = self._get_price_at_date(price_data, ticker, date)
                if price:
                    portfolio_value += shares * price

            portfolio_values.append(portfolio_value)
            dates.append(date.isoformat() if isinstance(date, datetime) else str(date))

        return portfolio_values, trades, dates

    def _should_rebalance(
        self,
        last_rebalance: datetime,
        current_date: datetime,
        frequency: str
    ) -> bool:
        """Check if rebalance should occur"""
        delta_map = {"monthly": 30, "quarterly": 90, "yearly": 365}
        delta = delta_map.get(frequency, 90)
        return (current_date - last_rebalance).days >= delta

    def _get_inflation_beaters_at_date(
        self,
        date: datetime,
        min_excess: float
    ) -> List[Dict]:
        """Get inflation beaters as of specific date"""
        beaters = self.session.query(
            Company.ticker,
            Company.name,
            InflationPerformance.excess_return_3yr
        ).join(InflationPerformance).filter(
            and_(
                Company.is_active == True,
                InflationPerformance.excess_return_3yr >= min_excess
            )
        ).order_by(
            InflationPerformance.excess_return_3yr.desc()
        ).all()

        return [
            {
                'ticker': b[0],
                'name': b[1],
                'excess_return': float(b[2])
            }
            for b in beaters
        ]

    def _get_price_at_date(
        self,
        price_data: pd.DataFrame,
        ticker: str,
        date
    ) -> Optional[float]:
        """Get price for ticker at or before specific date"""
        ticker_data = price_data[price_data['ticker'] == ticker]
        ticker_data = ticker_data[
            pd.to_datetime(ticker_data['date']) <= pd.Timestamp(date)
        ]

        if ticker_data.empty:
            return None

        latest = ticker_data.sort_values('date').iloc[-1]
        return float(latest['close'])

    def _calculate_metrics(
        self,
        portfolio_values: List[float],
        trades: List[Dict],
        initial_capital: float,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """Calculate performance metrics"""
        pv = np.array(portfolio_values)

        if len(pv) < 2 or pv[0] == 0:
            return {
                "total_return": 0, "annual_return": 0, "max_drawdown": 0,
                "sharpe_ratio": 0, "num_trades": len(trades), "num_buys": 0,
                "num_sells": 0, "win_rate": 0, "profit_factor": 0,
                "final_value": round(float(pv[-1]) if len(pv) else initial_capital, 2),
                "total_profit_loss": 0, "daily_volatility": 0,
                "best_day": 0, "worst_day": 0
            }

        total_return = (pv[-1] - pv[0]) / pv[0] * 100

        days = (end_date - start_date).days
        years = max(days / 365.25, 0.01)
        annual_return = ((pv[-1] / pv[0]) ** (1 / years) - 1) * 100

        running_max = np.maximum.accumulate(pv)
        drawdown = (pv - running_max) / running_max
        max_drawdown = float(np.min(drawdown)) * 100

        returns = np.diff(pv) / pv[:-1]

        # Sharpe ratio using CBN MPR 18.75% as risk-free rate
        risk_free_rate = 0.1875 / 365
        excess_returns = returns - risk_free_rate
        sharpe_ratio = (
            float(np.mean(excess_returns)) / float(np.std(excess_returns)) * np.sqrt(252)
            if float(np.std(excess_returns)) > 0 else 0
        )

        buy_trades = [t for t in trades if t['action'] == 'BUY']
        sell_trades = [t for t in trades if t['action'] == 'SELL']

        profitable_trades = 0
        total_profit = 0
        total_loss = 0

        for sell in sell_trades:
            matching_buys = [b for b in buy_trades if b['ticker'] == sell['ticker']]
            if matching_buys:
                buy = matching_buys[-1]
                profit = (sell['price'] - buy['price']) * sell['shares']
                if profit > 0:
                    profitable_trades += 1
                    total_profit += profit
                else:
                    total_loss += abs(profit)

        win_rate = (profitable_trades / len(sell_trades) * 100) if sell_trades else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

        return {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "num_trades": len(trades),
            "num_buys": len(buy_trades),
            "num_sells": len(sell_trades),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "final_value": round(float(pv[-1]), 2),
            "total_profit_loss": round(float(pv[-1]) - initial_capital, 2),
            "daily_volatility": round(float(np.std(returns)) * 100, 2),
            "best_day": round(float(np.max(returns)) * 100, 2),
            "worst_day": round(float(np.min(returns)) * 100, 2)
        }

    def _compare_results(self, results: Dict) -> Dict:
        """Compare strategy results"""
        comparison = {}
        for strategy_name, result in results.items():
            if strategy_name != "comparison_summary" and "metrics" in result:
                comparison[strategy_name] = {
                    "total_return": result['metrics']['total_return'],
                    "annual_return": result['metrics']['annual_return'],
                    "sharpe_ratio": result['metrics']['sharpe_ratio'],
                    "max_drawdown": result['metrics']['max_drawdown']
                }
        return comparison


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    DATABASE_URL = os.getenv("DATABASE_URL")
    backtest = NGXBacktestEngine(DATABASE_URL)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 3)

    print("Backtesting Inflation-Beating Strategy...")
    result = backtest.backtest_inflation_strategy(
        start_date, end_date,
        initial_capital=1_000_000,
        portfolio_size=10,
        rebalance_frequency="quarterly"
    )

    if "metrics" in result:
        print("\n=== BACKTEST RESULTS ===")
        for k, v in result['metrics'].items():
            print(f"{k}: {v}")
