"""
Backtesting API Router
Mounted at /api/backtest in main.py via app.include_router()
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv()

from backtesting_engine import NGXBacktestEngine

router = APIRouter(prefix="/api/backtest", tags=["backtesting"])

# Lazy-initialised — engine is created on first request, not at import time.
# This prevents a crash when DATABASE_URL is not yet available at startup.
_backtest_engine: Optional[NGXBacktestEngine] = None


def get_engine() -> NGXBacktestEngine:
    global _backtest_engine
    if _backtest_engine is None:
        url = (os.getenv("DATABASE_URL") or "").strip()
        if not url:
            raise HTTPException(status_code=503, detail="DATABASE_URL environment variable is not set")
        _backtest_engine = NGXBacktestEngine(url)
    return _backtest_engine


# ==================== PYDANTIC MODELS ====================

class BacktestInflationStrategyRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 1_000_000
    portfolio_size: int = 10
    rebalance_frequency: str = "quarterly"
    min_excess_return: float = 5.0


class BacktestBuyHoldRequest(BaseModel):
    tickers: List[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 1_000_000


# ==================== HELPERS ====================

def _parse_dates(start_date: Optional[str], end_date: Optional[str]):
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else end_dt - timedelta(days=365 * 3)
    if start_dt >= end_dt:
        raise ValueError("start_date must be before end_date")
    return start_dt, end_dt


# ==================== ENDPOINTS ====================

@router.post("/inflation-strategy")
async def backtest_inflation_strategy(request: BacktestInflationStrategyRequest):
    """Backtest the inflation-beating strategy (JSON body)"""
    try:
        start_dt, end_dt = _parse_dates(request.start_date, request.end_date)
        result = get_engine().backtest_inflation_strategy(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=request.initial_capital,
            portfolio_size=request.portfolio_size,
            rebalance_frequency=request.rebalance_frequency,
            min_excess_return_threshold=request.min_excess_return,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buy-hold")
async def backtest_buy_hold(request: BacktestBuyHoldRequest):
    """Backtest buy-and-hold strategy (JSON body)"""
    try:
        if not request.tickers:
            raise ValueError("At least one ticker is required")
        start_dt, end_dt = _parse_dates(request.start_date, request.end_date)
        result = get_engine().backtest_buy_and_hold(
            tickers=request.tickers,
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=request.initial_capital,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
async def compare_strategies(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    initial_capital: float = Query(1_000_000),
):
    """Compare inflation-beating vs top-10 buy-and-hold"""
    try:
        start_dt, end_dt = _parse_dates(start_date, end_date)
        results = get_engine().compare_strategies(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=initial_capital,
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BacktestDevaluationRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 1_000_000
    portfolio_size: int = 10


@router.post("/devaluation-strategy")
async def backtest_devaluation(request: BacktestDevaluationRequest):
    """Backtest FX Revenue Filter strategy — stocks that hedge naira devaluation"""
    try:
        start_dt, end_dt = _parse_dates(request.start_date, request.end_date)
        result = get_engine().backtest_devaluation_strategy(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=request.initial_capital,
            portfolio_size=request.portfolio_size,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics-explanation")
async def metrics_explanation():
    """Explain what each backtest metric means"""
    return {
        "metrics": {
            "total_return": "Total percentage return from start to end of backtest period",
            "annual_return": "Annualized return (compounded yearly growth rate)",
            "sharpe_ratio": "Risk-adjusted return vs CBN MPR 18.75%. >1 is good, >2 is excellent",
            "max_drawdown": "Largest peak-to-trough decline (%)",
            "daily_volatility": "Daily price volatility (%)",
            "best_day": "Best single day return (%)",
            "worst_day": "Worst single day return (%)",
            "num_trades": "Total buy/sell transactions",
            "win_rate": "Percentage of trades that were profitable",
            "profit_factor": "Ratio of gross profit to gross loss (>1 is profitable)",
            "final_value": "Final portfolio value in naira",
        },
        "interpretation": {
            "good_annual_return": "35%+ (must beat Nigerian inflation)",
            "good_sharpe_ratio": "1.0+",
            "acceptable_max_drawdown": "-30% or better",
            "good_win_rate": "50%+",
        },
    }


@router.get("/preset-periods")
async def preset_periods():
    """Common backtest date ranges"""
    end = datetime.now()
    fmt = "%Y-%m-%d"
    return {
        "one_year": {
            "start_date": (end - timedelta(days=365)).strftime(fmt),
            "end_date": end.strftime(fmt),
        },
        "three_years": {
            "start_date": (end - timedelta(days=365 * 3)).strftime(fmt),
            "end_date": end.strftime(fmt),
        },
        "five_years": {
            "start_date": (end - timedelta(days=365 * 5)).strftime(fmt),
            "end_date": end.strftime(fmt),
        },
        "ten_years": {
            "start_date": (end - timedelta(days=365 * 10)).strftime(fmt),
            "end_date": end.strftime(fmt),
        },
    }
