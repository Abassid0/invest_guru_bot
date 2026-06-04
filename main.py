"""
Main FastAPI Application - Deployment Ready
Place this as main.py in your root directory
"""
import sys
import os
from pathlib import Path

# DNS patch: only on Windows local dev where router DNS fails for Supabase subdomains
if sys.platform == "win32":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dns_patch  # noqa: F401

from fastapi import Query

# Add current directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

# Import from local modules
from database.models import (
    create_database_engine, get_session,
    Company, StockPrice, InflationPerformance, InflationData, MacroIndicator
)
from calculators.inflation_calculator import InflationCalculator
from sqlalchemy import and_, func

# Initialize FastAPI
app = FastAPI(
    title="NGX Investment Intelligence API",
    version="1.0.0",
    description="Nigerian Stock Exchange Investment Analysis Platform"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Backtesting router (registered after env is loaded)
from backtest_api_routes import router as backtest_router
app.include_router(backtest_router)

# Database configuration
DATABASE_URL = (
    os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_INTERNAL") or ""
).strip()

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment variables")

# Initialize database connection
engine = create_database_engine(DATABASE_URL)

# Lazy — InflationCalculator holds a persistent session; defer until first use
_calculator = None

def get_calculator():
    global _calculator
    if _calculator is None:
        _calculator = InflationCalculator(DATABASE_URL)
    return _calculator


# ==================== PYDANTIC MODELS ====================

class StockBasic(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float
    change_percent: float
    has_fx_revenue: bool
    
    class Config:
        from_attributes = True

class StockDetail(BaseModel):
    ticker: str
    name: str
    sector: str
    listing_date: Optional[date] = None
    current_price: float
    change_percent: float
    volume: int
    has_fx_revenue: bool
    return_1yr: float
    return_3yr: float
    return_5yr: float
    excess_return_1yr: float
    excess_return_3yr: float
    excess_return_5yr: float
    beats_inflation: bool
    volatility_1yr: float
    risk_adjusted_return: float
    
    class Config:
        from_attributes = True

class InflationBeater(BaseModel):
    ticker: str
    name: str
    sector: str
    excess_return_3yr: float
    has_fx_revenue: bool
    current_price: float

class EmailSignup(BaseModel):
    email: EmailStr
    name: str
    frequency: str


# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """Lightweight liveness probe — no DB call so Railway health check always succeeds."""
    return {
        "status": "online",
        "service": "NGX Investment Intelligence API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Lightweight health check — returns 200 immediately for Railway probe."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/health/db")
async def db_health_check():
    """Full DB connectivity check (separate from Railway probe)."""
    try:
        session = get_session(engine)
        session.query(Company).first()
        session.close()

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


@app.get("/api/stocks", response_model=List[StockBasic])
async def get_all_stocks():
    """Get all active stocks with latest prices"""
    session = get_session(engine)
    
    try:
        stocks = []
        companies = session.query(Company).filter_by(is_active=True).all()
        
        for company in companies:
            latest_price = session.query(StockPrice).filter_by(
                company_id=company.id
            ).order_by(StockPrice.date.desc()).first()
            
            if latest_price:
                stocks.append(StockBasic(
                    ticker=company.ticker,
                    name=company.name,
                    sector=company.sector,
                    current_price=float(latest_price.close),
                    change_percent=float(latest_price.change_percent or 0),
                    has_fx_revenue=company.has_fx_revenue
                ))
        
        return stocks
    finally:
        session.close()


@app.get("/api/stocks/{ticker}", response_model=StockDetail)
async def get_stock_detail(ticker: str):
    """Get detailed information for a specific stock"""
    session = get_session(engine)
    
    try:
        company = session.query(Company).filter_by(ticker=ticker.upper()).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
        
        latest_price = session.query(StockPrice).filter_by(
            company_id=company.id
        ).order_by(StockPrice.date.desc()).first()
        
        performance = session.query(InflationPerformance).filter_by(
            company_id=company.id
        ).order_by(InflationPerformance.calculation_date.desc()).first()
        
        if not latest_price:
            raise HTTPException(status_code=404, detail=f"No price data for {ticker}")
        
        if not performance:
            raise HTTPException(status_code=404, detail=f"No performance data for {ticker}")
        
        return StockDetail(
            ticker=company.ticker,
            name=company.name,
            sector=company.sector,
            listing_date=company.listing_date,
            current_price=float(latest_price.close),
            change_percent=float(latest_price.change_percent or 0),
            volume=int(latest_price.volume or 0),
            has_fx_revenue=company.has_fx_revenue,
            return_1yr=float(performance.return_1yr or 0),
            return_3yr=float(performance.return_3yr or 0),
            return_5yr=float(performance.return_5yr or 0),
            excess_return_1yr=float(performance.excess_return_1yr or 0),
            excess_return_3yr=float(performance.excess_return_3yr or 0),
            excess_return_5yr=float(performance.excess_return_5yr or 0),
            beats_inflation=performance.beats_inflation_all or False,
            volatility_1yr=float(performance.volatility_1yr or 0),
            risk_adjusted_return=float(performance.risk_adjusted_return_3yr or 0)
        )
    finally:
        session.close()


@app.get("/api/inflation-beaters", response_model=List[InflationBeater])
async def get_inflation_beaters(min_excess: float = 0.0):
    """Get stocks that beat inflation"""
    try:
        beaters = get_calculator().get_inflation_beaters(min_excess_return_3yr=min_excess)
        
        result = []
        session = get_session(engine)
        
        try:
            for stock in beaters[:20]:
                company = session.query(Company).filter_by(ticker=stock['ticker']).first()
                if not company:
                    continue
                    
                latest_price = session.query(StockPrice).filter_by(
                    company_id=company.id
                ).order_by(StockPrice.date.desc()).first()
                
                result.append(InflationBeater(
                    ticker=stock['ticker'],
                    name=stock['name'],
                    sector=stock['sector'],
                    excess_return_3yr=stock['excess_return_3yr'],
                    has_fx_revenue=stock['has_fx_revenue'],
                    current_price=float(latest_price.close) if latest_price else 0
                ))
            
            return result
        finally:
            session.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sectors")
async def get_sectors():
    """Get sector performance summary"""
    session = get_session(engine)
    
    try:
        sectors = session.query(
            Company.sector,
            func.count(Company.id).label('count'),
            func.avg(InflationPerformance.excess_return_3yr).label('avg_excess')
        ).join(InflationPerformance).filter(
            Company.is_active == True
        ).group_by(Company.sector).all()
        
        return [
            {
                "sector": sector,
                "stock_count": count,
                "avg_excess_return": float(avg_excess or 0)
            }
            for sector, count, avg_excess in sectors
        ]
    finally:
        session.close()


@app.get("/api/macro")
async def get_macro_indicators():
    """Get latest Nigerian macro indicators"""
    session = get_session(engine)
    
    try:
        latest_macro = session.query(MacroIndicator).order_by(
            MacroIndicator.date.desc()
        ).first()
        
        latest_inflation = session.query(InflationData).order_by(
            InflationData.date.desc()
        ).first()
        
        if not latest_macro or not latest_inflation:
            raise HTTPException(status_code=404, detail="Macro data not available")
        
        return {
            "date": latest_macro.date.isoformat(),
            "cbm_mpr": float(latest_macro.mpr),
            "usd_ngn_official": float(latest_macro.usd_ngn_official),
            "usd_ngn_parallel": float(latest_macro.usd_ngn_parallel or 0),
            "inflation_rate": float(latest_inflation.headline_cpi),
            "food_inflation": float(latest_inflation.food_inflation or 0),
            "brent_crude": float(latest_macro.brent_crude_usd or 0),
            "treasury_bill_91d": float(latest_macro.treasury_bill_91d or 0)
        }
    finally:
        session.close()


@app.get("/api/search")
async def search_stocks(q: str):
    """Search stocks by ticker or name"""
    if not q or len(q) < 2:
        return []
    
    session = get_session(engine)
    
    try:
        results = session.query(Company).filter(
            and_(
                Company.is_active == True,
                (Company.ticker.ilike(f"%{q}%") | Company.name.ilike(f"%{q}%"))
            )
        ).limit(10).all()
        
        return [
            {
                "ticker": company.ticker,
                "name": company.name,
                "sector": company.sector
            }
            for company in results
        ]
    finally:
        session.close()


@app.post("/api/sync")
async def trigger_sync(admin_key: str = Query(...)):
    """Trigger a full data sync. Requires SYNC_KEY env var (or ADMIN_PASSWORD fallback)."""
    valid_key = os.getenv("SYNC_KEY") or os.getenv("ADMIN_PASSWORD", "")
    if admin_key != valid_key.strip():
        raise HTTPException(status_code=403, detail="Invalid admin key")
    from data_sync import run_full_sync
    result = run_full_sync()
    return {"status": "complete", "result": result}


@app.get("/api/sync/status")
async def sync_status():
    """Show latest price records count and freshness."""
    session = get_session(engine)
    try:
        from sqlalchemy import func
        latest_price = session.query(func.max(StockPrice.date)).scalar()
        price_count = session.query(StockPrice).count()
        latest_macro = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        return {
            "stock_prices": {
                "total_records": price_count,
                "latest_date": latest_price.isoformat() if latest_price else None,
                "is_today": latest_price == date.today() if latest_price else False,
            },
            "macro": {
                "latest_date": latest_macro.date.isoformat() if latest_macro else None,
                "usd_ngn": float(latest_macro.usd_ngn_official) if latest_macro else None,
            }
        }
    finally:
        session.close()


@app.post("/api/email-signup")
async def email_signup(signup: EmailSignup):
    """Sign up for email alerts"""
    # TODO: Implement actual email signup logic
    # For now, just log and return success
    
    print(f"New signup: {signup.email} ({signup.name}) - {signup.frequency}")
    
    return {
        "status": "success",
        "message": f"Successfully subscribed {signup.email} to {signup.frequency} updates"
    }


# ==================== TELEGRAM WEBHOOK ====================

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Stores the last incoming message for debugging — cleared on each message
_last_message: dict = {}


async def _tg_send(chat_id: int, text: str) -> dict:
    """Send a message to a Telegram chat. Returns the Telegram API response."""
    import httpx
    # Use plain text to avoid Markdown parse errors
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    return r.json()


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram updates and respond using Claude."""
    from claude_client import get_client, NGX_SYSTEM_PROMPT

    try:
        data = await request.json()
    except Exception:
        return {"ok": False}

    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    user_name = message.get("from", {}).get("first_name", "Investor")

    # Store for /telegram-webhook/last-message diagnostic
    _last_message.update({
        "chat_id": chat_id,
        "user_id": message.get("from", {}).get("id"),
        "username": message.get("from", {}).get("username"),
        "first_name": user_name,
        "text": text,
    })

    if not text:
        return {"ok": True}

    HELP = (
        "NGX Investment Intelligence Bot - @Naija_Guru_Bot\n\n"
        "EQUITIES\n"
        "/analyse TICKER - market & sector analysis\n"
        "/technical TICKER - chart signals (entry, SL, TP)\n"
        "/fullanalysis TICKER - full institutional report\n"
        "/financials TICKER - 5yr forensic breakdown\n"
        "/moat TICKER - competitive moat score\n"
        "/value TICKER - valuation + price target\n"
        "/risk TICKER - risk matrix + stop-loss\n"
        "/growth TICKER - growth scenarios\n"
        "/institutional TICKER - hedge fund view\n"
        "/debate TICKER - bull vs bear verdict\n"
        "/earnings TICKER - earnings scorecard\n"
        "/sentiment TICKER - bullish/bearish gauge\n\n"
        "FIXED INCOME & FUNDS\n"
        "/tbills - NTB & OMO auction rates\n"
        "/bonds - FGN Bond yield curve\n"
        "/funds - mutual fund NAV comparison\n"
        "/compare - fixed income vs equities\n\n"
        "MACRO & PORTFOLIO\n"
        "/macro - CBN, inflation, FX rates\n"
        "/portfolio GTCO DANGCEM - diversification\n"
        "/global EVENT - geopolitical impact on NGX\n"
        "/dividend - best yield plays\n\n"
        "Or just type any investment question!"
    )

    # /start  /help
    if text.startswith("/start") or text.startswith("/help"):
        await _tg_send(chat_id, f"Welcome {user_name}!\n\n" + HELP)
        return {"ok": True}

    # /macro — served directly from DB, no Claude needed
    if text.startswith("/macro"):
        try:
            session = get_session(engine)
            macro = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
            inflation = session.query(InflationData).order_by(InflationData.date.desc()).first()
            session.close()
            if macro and inflation:
                await _tg_send(chat_id,
                    f"Nigerian Macro - {macro.date.strftime('%b %Y')}\n\n"
                    f"CBN MPR: {float(macro.mpr):.2f}%\n"
                    f"Inflation (headline): {float(inflation.headline_cpi):.2f}%\n"
                    f"Food Inflation: {float(inflation.food_inflation):.2f}%\n"
                    f"USD/NGN Official: N{float(macro.usd_ngn_official):,.0f}\n"
                    f"USD/NGN Parallel: N{float(macro.usd_ngn_parallel):,.0f}\n"
                    f"91-day T-bill: {float(macro.treasury_bill_91d):.2f}%\n"
                    f"Brent Crude: ${float(macro.brent_crude_usd):.0f}\n\n"
                    "Use /compare to see how T-bills stack up vs equities."
                )
                return {"ok": True}
            await _tg_send(chat_id, "Macro data not seeded yet. Contact admin.")
        except Exception as e:
            await _tg_send(chat_id, f"Error: {str(e)[:200]}")
        return {"ok": True}

    # Build a focused prompt for structured commands
    COMMAND_PROMPTS = {
        "/analyse":      "Provide a concise market and sector analysis for NGX stock: {arg}",
        "/technical":    "Provide technical analysis with entry price, stop-loss, and take-profit targets for NGX stock: {arg}",
        "/fullanalysis": "Provide a full institutional-grade investment report for NGX stock: {arg}",
        "/financials":   "Provide a 5-year forensic financial breakdown for NGX stock: {arg}",
        "/moat":         "Assess the competitive moat score and durability for NGX stock: {arg}",
        "/value":        "Provide DCF valuation and naira price target for NGX stock: {arg}",
        "/risk":         "Provide a risk matrix and stop-loss table for NGX stock: {arg}",
        "/growth":       "Provide bull, base, and bear growth scenarios for NGX stock: {arg}",
        "/institutional":"Give an institutional/hedge fund perspective on NGX stock: {arg}",
        "/debate":       "Provide a structured bull vs bear debate verdict for NGX stock: {arg}",
        "/earnings":     "Provide an earnings scorecard and EPS analysis for NGX stock: {arg}",
        "/sentiment":    "Provide bullish/bearish sentiment gauge for NGX stock: {arg}",
        "/tbills":       "Summarise current NTB and OMO auction rates in Nigeria.",
        "/bonds":        "Summarise the current FGN Bond yield curve.",
        "/funds":        "Compare top Nigerian mutual fund NAVs and returns.",
        "/compare":      "Compare Nigerian fixed income (T-bills, bonds) vs NGX equities now.",
        "/dividend":     "List the best dividend yield plays on NGX including mutual funds.",
        "/portfolio":    "Provide portfolio diversification advice for these NGX tickers: {arg}",
        "/global":       "Analyse the geopolitical/global event impact on Nigerian markets: {arg}",
    }

    claude_prompt = text
    for cmd, template in COMMAND_PROMPTS.items():
        if text.lower().startswith(cmd):
            arg = text[len(cmd):].strip().upper() or "NGX market"
            claude_prompt = template.format(arg=arg)
            break

    # All commands and free-text -> Claude with web search for live data
    try:
        from claude_client import run_analysis
        reply = run_analysis(claude_prompt, max_tokens=1500)
        await _tg_send(chat_id, reply[:3800])
    except Exception as e:
        await _tg_send(chat_id, f"Analysis unavailable: {str(e)[:200]}")

    return {"ok": True}


@app.get("/telegram-webhook/last-message")
async def last_message():
    """Returns the last message received from Telegram — shows the real chat_id."""
    if not _last_message:
        return {"info": "No messages received yet. Send any message to @Naija_Guru_Bot first."}
    return _last_message


@app.get("/telegram-webhook/debug")
async def telegram_debug():
    """Diagnose bot token, getMe, and webhook info."""
    import httpx
    token = TELEGRAM_BOT_TOKEN
    masked = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else "NOT SET"
    results = {"token_set": bool(token), "token_preview": masked, "token_length": len(token)}
    async with httpx.AsyncClient(timeout=10) as client:
        me = await client.get(f"{TELEGRAM_API}/getMe")
        results["getMe"] = me.json()
        wi = await client.get(f"{TELEGRAM_API}/getWebhookInfo")
        results["webhook_info"] = wi.json()
    return results


@app.get("/telegram-webhook/send-test")
async def send_test(chat_id: int, message: str = "Bot is working!"):
    """Send a test message to a specific chat_id to confirm send works."""
    result = await _tg_send(chat_id, message)
    return {"sent_to": chat_id, "telegram_response": result}


@app.get("/telegram-webhook/register")
async def register_webhook():
    """Register the webhook URL with Telegram. Call once after deploy."""
    import httpx
    webhook_url = f"https://{os.getenv('WEBHOOK_URL', '').strip()}/telegram-webhook"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "edited_message"]},
        )
    result = r.json()
    return {"webhook_url": webhook_url, "telegram_response": result}


@app.get("/telegram-webhook/info")
async def webhook_info():
    """Check current webhook registration status."""
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
        )
    return r.json()


# ==================== DASHBOARD ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NGX Investment Intelligence</title>
  <script src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    nav { background: #1e293b; padding: 1rem 2rem; display: flex; gap: 1rem; align-items: center; border-bottom: 1px solid #334155; }
    nav h1 { font-size: 1.2rem; font-weight: 700; color: #38bdf8; flex: 1; }
    nav button { background: transparent; border: 1px solid #334155; color: #94a3b8; padding: 0.4rem 1rem; border-radius: 6px; cursor: pointer; transition: all .2s; }
    nav button.active, nav button:hover { background: #0ea5e9; border-color: #0ea5e9; color: #fff; }
    main { max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
    .card h2 { font-size: 1.1rem; font-weight: 600; color: #38bdf8; margin-bottom: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }
    .metric { background: #0f172a; border-radius: 8px; padding: 1rem; text-align: center; }
    .metric .label { font-size: .75rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }
    .metric .value { font-size: 1.6rem; font-weight: 700; margin-top: .25rem; }
    .pos { color: #34d399; } .neg { color: #f87171; } .neu { color: #fbbf24; }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
    label { display: flex; flex-direction: column; gap: .3rem; font-size: .85rem; color: #94a3b8; }
    input, select { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: .5rem .75rem; border-radius: 6px; font-size: .9rem; }
    input:focus, select:focus { outline: none; border-color: #0ea5e9; }
    .btn { background: #0ea5e9; color: #fff; border: none; padding: .6rem 1.5rem; border-radius: 8px; cursor: pointer; font-size: .95rem; font-weight: 600; transition: background .2s; }
    .btn:hover { background: #0284c7; }
    .btn:disabled { background: #334155; cursor: not-allowed; }
    .error { color: #f87171; background: #450a0a; border: 1px solid #991b1b; border-radius: 8px; padding: .75rem 1rem; margin-bottom: 1rem; }
    .trades-table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    .trades-table th { text-align: left; padding: .5rem .75rem; color: #64748b; border-bottom: 1px solid #334155; }
    .trades-table td { padding: .5rem .75rem; border-bottom: 1px solid #1e293b; }
    .badge { display: inline-block; padding: .15rem .5rem; border-radius: 4px; font-size: .75rem; font-weight: 600; }
    .badge-buy { background: #064e3b; color: #34d399; }
    .badge-sell { background: #450a0a; color: #f87171; }
    .compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
  </style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const { useState } = React;
const API_BASE = '/api';

function BacktestPage({ setPage }) {
  const [backtest, setBacktest] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [params, setParams] = useState({
    startDate: '2023-01-01',
    endDate: new Date().toISOString().split('T')[0],
    initialCapital: 1000000,
    portfolioSize: 10,
    rebalanceFreq: 'quarterly',
    minExcess: 5.0
  });

  const runBacktest = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/backtest/inflation-strategy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: params.startDate,
          end_date: params.endDate,
          initial_capital: params.initialCapital,
          portfolio_size: params.portfolioSize,
          rebalance_frequency: params.rebalanceFreq,
          min_excess_return: params.minExcess
        })
      });

      const data = await response.json();
      setBacktest(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <button
        onClick={() => setPage('home')}
        className="mb-4 text-purple-600 hover:underline"
      >
        ← Back
      </button>

      <div className="bg-gradient-to-r from-blue-500 to-purple-600 text-white p-8 rounded-lg mb-8">
        <h1 className="text-3xl font-bold mb-2">📊 Backtest Strategy</h1>
        <p>Test how efficient your investment strategy would have been historically</p>
      </div>

      {/* Parameters */}
      <div className="bg-white p-6 rounded-lg shadow mb-6">
        <h2 className="text-xl font-bold mb-4">Strategy Parameters</h2>

        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium mb-2">Start Date</label>
            <input
              type="date"
              value={params.startDate}
              onChange={(e) => setParams({...params, startDate: e.target.value})}
              className="w-full px-4 py-2 border rounded"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">End Date</label>
            <input
              type="date"
              value={params.endDate}
              onChange={(e) => setParams({...params, endDate: e.target.value})}
              className="w-full px-4 py-2 border rounded"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Initial Capital (₦)</label>
            <input
              type="number"
              value={params.initialCapital}
              onChange={(e) => setParams({...params, initialCapital: Number(e.target.value)})}
              className="w-full px-4 py-2 border rounded"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Portfolio Size</label>
            <select
              value={params.portfolioSize}
              onChange={(e) => setParams({...params, portfolioSize: Number(e.target.value)})}
              className="w-full px-4 py-2 border rounded"
            >
              <option value="5">5 stocks</option>
              <option value="10">10 stocks</option>
              <option value="15">15 stocks</option>
              <option value="20">20 stocks</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Rebalance Frequency</label>
            <select
              value={params.rebalanceFreq}
              onChange={(e) => setParams({...params, rebalanceFreq: e.target.value})}
              className="w-full px-4 py-2 border rounded"
            >
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Min 3yr Excess Return (%)</label>
            <input
              type="number"
              value={params.minExcess}
              onChange={(e) => setParams({...params, minExcess: Number(e.target.value)})}
              className="w-full px-4 py-2 border rounded"
            />
          </div>
        </div>

        <button
          onClick={runBacktest}
          disabled={loading}
          className="mt-6 w-full px-6 py-3 bg-purple-600 text-white rounded-lg font-semibold hover:bg-purple-700 disabled:bg-gray-400"
        >
          {loading ? 'Running backtest...' : 'Run Backtest'}
        </button>
      </div>

      {/* Results */}
      {backtest && !error && (
        <div className="bg-white rounded-lg shadow p-8">
          <h2 className="text-2xl font-bold mb-6">📈 Results</h2>

          {/* Metrics Grid */}
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <div className="bg-blue-50 p-6 rounded">
              <div className="text-sm text-gray-600">Total Return</div>
              <div className={`text-3xl font-bold ${backtest.metrics.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {backtest.metrics.total_return >= 0 ? '+' : ''}{backtest.metrics.total_return.toFixed(2)}%
              </div>
            </div>

            <div className="bg-green-50 p-6 rounded">
              <div className="text-sm text-gray-600">Annual Return</div>
              <div className={`text-3xl font-bold ${backtest.metrics.annual_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {backtest.metrics.annual_return >= 0 ? '+' : ''}{backtest.metrics.annual_return.toFixed(2)}%
              </div>
            </div>

            <div className="bg-purple-50 p-6 rounded">
              <div className="text-sm text-gray-600">Sharpe Ratio</div>
              <div className="text-3xl font-bold text-purple-600">
                {backtest.metrics.sharpe_ratio.toFixed(2)}
              </div>
            </div>

            <div className="bg-red-50 p-6 rounded">
              <div className="text-sm text-gray-600">Max Drawdown</div>
              <div className="text-3xl font-bold text-red-600">
                {backtest.metrics.max_drawdown.toFixed(2)}%
              </div>
            </div>
          </div>

          {/* Trading Metrics */}
          <div className="grid md:grid-cols-3 gap-4">
            <div className="p-4 border rounded">
              <div className="font-semibold">Total Trades</div>
              <div className="text-2xl">{backtest.metrics.num_trades}</div>
            </div>

            <div className="p-4 border rounded">
              <div className="font-semibold">Win Rate</div>
              <div className="text-2xl text-green-600">{backtest.metrics.win_rate.toFixed(1)}%</div>
            </div>

            <div className="p-4 border rounded">
              <div className="font-semibold">Final Value</div>
              <div className="text-2xl">₦{backtest.metrics.final_value.toLocaleString()}</div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          Error: {error}
        </div>
      )}
    </div>
  );
}

function HomePage({ setPage }) {
  return (
    <div className="max-w-4xl mx-auto text-center py-20">
      <h1 className="text-4xl font-bold mb-4 text-gray-800">NGX Investment Intelligence</h1>
      <p className="text-gray-500 mb-10 text-lg">Nigerian Stock Exchange Analysis Platform</p>
      <button
        onClick={() => setPage('backtest')}
        className="px-8 py-4 bg-purple-600 text-white rounded-lg font-semibold hover:bg-purple-700 text-lg"
      >
        📊 Open Backtest Dashboard
      </button>
    </div>
  );
}

function App() {
  const [page, setPage] = useState('backtest');
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b px-6 py-4 flex items-center gap-4 shadow-sm">
        <h1 className="text-xl font-bold text-purple-700 flex-1">NGX Investment Intelligence</h1>
        <button
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${page === 'backtest' ? 'bg-purple-600 text-white' : 'text-gray-600 hover:bg-gray-100'}`}
          onClick={() => setPage('backtest')}
        >
          Backtest
        </button>
      </nav>
      <main className="p-6">
        {page === 'home' && <HomePage setPage={setPage} />}
        {page === 'backtest' && <BacktestPage setPage={setPage} />}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the backtesting web dashboard"""
    return HTMLResponse(content=DASHBOARD_HTML)



# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
