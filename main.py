"""
NGX Investment Intelligence API — slim entrypoint.
All Telegram/Paystack/referral logic lives in bot/ package.
"""
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dns_patch  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv
load_dotenv()

from database.models import (
    create_database_engine, get_session,
    Company, StockPrice, InflationPerformance, InflationData, MacroIndicator,
)
from calculators.inflation_calculator import InflationCalculator
from sqlalchemy import and_, func

from backtest_api_routes import router as backtest_router

app = FastAPI(
    title="NGX Investment Intelligence API",
    version="2.0.0",
    description="Nigerian Stock Exchange Investment Analysis Platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest_router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_INTERNAL") or "").strip()
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment variables")

engine = create_database_engine(DATABASE_URL)

_calculator = None
def get_calculator():
    global _calculator
    if _calculator is None:
        _calculator = InflationCalculator(DATABASE_URL)
    return _calculator

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ── Pydantic models ──────────────────────────────────────────────────────────

class StockBasic(BaseModel):
    ticker: str; name: str; sector: str; current_price: float
    change_percent: float; has_fx_revenue: bool
    class Config:
        from_attributes = True

class StockDetail(BaseModel):
    ticker: str; name: str; sector: str; listing_date: Optional[date] = None
    current_price: float; change_percent: float; volume: int; has_fx_revenue: bool
    return_1yr: float; return_3yr: float; return_5yr: float
    excess_return_1yr: float; excess_return_3yr: float; excess_return_5yr: float
    beats_inflation: bool; volatility_1yr: float; risk_adjusted_return: float
    class Config:
        from_attributes = True

class InflationBeater(BaseModel):
    ticker: str; name: str; sector: str; excess_return_3yr: float
    has_fx_revenue: bool; current_price: float

class EmailSignup(BaseModel):
    email: EmailStr; name: str; frequency: str


# ── Health & root ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "online", "service": "NGX Investment Intelligence API", "version": "2.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/health/db")
async def db_health_check():
    try:
        session = get_session(engine)
        session.query(Company).first()
        session.close()
        return {"status": "healthy", "database": "connected", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/stocks", response_model=List[StockBasic])
async def get_all_stocks():
    session = get_session(engine)
    try:
        stocks = []
        for company in session.query(Company).filter_by(is_active=True).all():
            lp = session.query(StockPrice).filter_by(company_id=company.id).order_by(StockPrice.date.desc()).first()
            if lp:
                stocks.append(StockBasic(
                    ticker=company.ticker, name=company.name, sector=company.sector,
                    current_price=float(lp.close), change_percent=float(lp.change_percent or 0),
                    has_fx_revenue=company.has_fx_revenue,
                ))
        return stocks
    finally:
        session.close()

@app.get("/api/stocks/{ticker}", response_model=StockDetail)
async def get_stock_detail(ticker: str):
    session = get_session(engine)
    try:
        company = session.query(Company).filter_by(ticker=ticker.upper()).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
        lp = session.query(StockPrice).filter_by(company_id=company.id).order_by(StockPrice.date.desc()).first()
        perf = session.query(InflationPerformance).filter_by(company_id=company.id).order_by(InflationPerformance.calculation_date.desc()).first()
        if not lp:
            raise HTTPException(status_code=404, detail=f"No price data for {ticker}")
        if not perf:
            raise HTTPException(status_code=404, detail=f"No performance data for {ticker}")
        return StockDetail(
            ticker=company.ticker, name=company.name, sector=company.sector,
            listing_date=company.listing_date, current_price=float(lp.close),
            change_percent=float(lp.change_percent or 0), volume=int(lp.volume or 0),
            has_fx_revenue=company.has_fx_revenue,
            return_1yr=float(perf.return_1yr or 0), return_3yr=float(perf.return_3yr or 0),
            return_5yr=float(perf.return_5yr or 0),
            excess_return_1yr=float(perf.excess_return_1yr or 0),
            excess_return_3yr=float(perf.excess_return_3yr or 0),
            excess_return_5yr=float(perf.excess_return_5yr or 0),
            beats_inflation=perf.beats_inflation_all or False,
            volatility_1yr=float(perf.volatility_1yr or 0),
            risk_adjusted_return=float(perf.risk_adjusted_return_3yr or 0),
        )
    finally:
        session.close()

@app.get("/api/inflation-beaters", response_model=List[InflationBeater])
async def get_inflation_beaters(min_excess: float = 0.0):
    try:
        beaters = get_calculator().get_inflation_beaters(min_excess_return_3yr=min_excess)
        result = []
        session = get_session(engine)
        try:
            for stock in beaters[:20]:
                company = session.query(Company).filter_by(ticker=stock['ticker']).first()
                if not company:
                    continue
                lp = session.query(StockPrice).filter_by(company_id=company.id).order_by(StockPrice.date.desc()).first()
                result.append(InflationBeater(
                    ticker=stock['ticker'], name=stock['name'], sector=stock['sector'],
                    excess_return_3yr=stock['excess_return_3yr'],
                    has_fx_revenue=stock['has_fx_revenue'],
                    current_price=float(lp.close) if lp else 0,
                ))
            return result
        finally:
            session.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sectors")
async def get_sectors():
    session = get_session(engine)
    try:
        sectors = session.query(
            Company.sector, func.count(Company.id).label('count'),
            func.avg(InflationPerformance.excess_return_3yr).label('avg_excess'),
        ).join(InflationPerformance).filter(Company.is_active == True).group_by(Company.sector).all()
        return [{"sector": s, "stock_count": c, "avg_excess_return": float(a or 0)} for s, c, a in sectors]
    finally:
        session.close()

@app.get("/api/macro")
async def get_macro_indicators():
    session = get_session(engine)
    try:
        m = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        i = session.query(InflationData).order_by(InflationData.date.desc()).first()
        if not m or not i:
            raise HTTPException(status_code=404, detail="Macro data not available")
        return {
            "date": m.date.isoformat(), "cbm_mpr": float(m.mpr),
            "usd_ngn_official": float(m.usd_ngn_official),
            "usd_ngn_parallel": float(m.usd_ngn_parallel or 0),
            "inflation_rate": float(i.headline_cpi),
            "food_inflation": float(i.food_inflation or 0),
            "brent_crude": float(m.brent_crude_usd or 0),
            "treasury_bill_91d": float(m.treasury_bill_91d or 0),
        }
    finally:
        session.close()

@app.get("/api/search")
async def search_stocks(q: str):
    if not q or len(q) < 2:
        return []
    session = get_session(engine)
    try:
        results = session.query(Company).filter(
            and_(Company.is_active == True, (Company.ticker.ilike(f"%{q}%") | Company.name.ilike(f"%{q}%")))
        ).limit(10).all()
        return [{"ticker": c.ticker, "name": c.name, "sector": c.sector} for c in results]
    finally:
        session.close()

@app.get("/api/sync/key-check")
async def sync_key_check(admin_key: str = Query(...)):
    valid_key = (os.getenv("SYNC_KEY") or os.getenv("ADMIN_PASSWORD") or "").strip()
    return {"match": admin_key == valid_key, "received_length": len(admin_key), "stored_length": len(valid_key)}

@app.post("/api/sync")
async def trigger_sync(admin_key: str = Query(...)):
    valid_key = (os.getenv("SYNC_KEY") or os.getenv("ADMIN_PASSWORD") or "").strip()
    if admin_key != valid_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    from data_sync import run_full_sync
    result = run_full_sync()
    return {"status": "complete", "result": result}

@app.get("/api/sync/status")
async def sync_status():
    session = get_session(engine)
    try:
        count = session.query(StockPrice).count()
        latest = session.query(StockPrice).order_by(StockPrice.date.desc()).first()
        return {
            "total_price_records": count,
            "latest_date": latest.date.isoformat() if latest else None,
        }
    finally:
        session.close()


# ── Paystack payment endpoints ────────────────────────────────────────────────

@app.get("/payment-success", response_class=HTMLResponse)
async def payment_success(reference: str = "", trxref: str = ""):
    from bot.paystack import verify_and_credit, RECEIPT_HTML_TEMPLATE, _tg_send
    ref = reference or trxref
    if not ref:
        return HTMLResponse("<h2>Invalid payment reference.</h2>", status_code=400)
    try:
        result = await verify_and_credit(ref, engine)
    except Exception as e:
        return HTMLResponse(f"<h2>Verification error: {e}</h2>", status_code=500)

    if "error" in result:
        return HTMLResponse(f"<h2>Payment could not be verified.</h2><p>{result['error']}</p>", status_code=400)

    plan = result["plan"]
    await _tg_send(result["telegram_id"],
        f"Payment confirmed!\n\nPlan: {plan['name']}\nCredits added: {plan['credits']}\n"
        f"New balance: {result['new_balance']} credits\n\nReference: {ref}\nType any command to start analysing!",
        TELEGRAM_API,
    )
    return HTMLResponse(content=RECEIPT_HTML_TEMPLATE.format(
        credits=plan["credits"], plan_name=plan["name"],
        amount_ngn=f"{result['amount_ngn']:,.0f}", paid_at=result["paid_at"],
        credits_before=result["new_balance"] - plan["credits"],
        credits_after=result["new_balance"], reference=ref,
    ))

@app.get("/api/payment/test")
async def test_paystack():
    import httpx
    secret = (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not secret:
        return {"error": "PAYSTACK_SECRET_KEY not set"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.paystack.co/transaction/initialize",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            json={"email": "test@ngxbot.app", "amount": 10000, "currency": "NGN"},
        )
    return {"http_status": r.status_code, "paystack_response": r.json()}

@app.post("/api/payment/webhook")
async def paystack_webhook(request: Request):
    from bot.paystack import handle_paystack_webhook
    body = await request.body()
    sig = request.headers.get("x-paystack-signature", "")
    result = await handle_paystack_webhook(body, sig, engine, TELEGRAM_API)
    if "error" in result and result["error"] == "Invalid signature":
        raise HTTPException(status_code=401, detail="Invalid signature")
    return {"ok": True}


# ── Telegram webhook ──────────────────────────────────────────────────────────

_last_message: dict = {}

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    from bot.handlers import handle_telegram_message
    try:
        data = await request.json()
    except Exception:
        return {"ok": False}

    message = data.get("message") or data.get("edited_message")
    if message:
        tg_user = message.get("from", {})
        _last_message.update({
            "chat_id": message["chat"]["id"], "user_id": tg_user.get("id"),
            "username": tg_user.get("username", ""), "text": (message.get("text") or "")[:100],
        })

    return await handle_telegram_message(data, engine, TELEGRAM_API)

@app.get("/telegram-webhook/last-message")
async def last_message():
    if not _last_message:
        return {"info": "No messages received yet. Send any message to @Naija_Guru_Bot first."}
    return _last_message

@app.get("/telegram-webhook/debug")
async def telegram_debug():
    import httpx
    token = TELEGRAM_BOT_TOKEN
    masked = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else "NOT SET"
    results = {"token_set": bool(token), "token_preview": masked}
    async with httpx.AsyncClient(timeout=10) as client:
        me = await client.get(f"{TELEGRAM_API}/getMe")
        results["getMe"] = me.json()
        wi = await client.get(f"{TELEGRAM_API}/getWebhookInfo")
        results["webhook_info"] = wi.json()
    return results

@app.get("/telegram-webhook/register")
async def register_webhook():
    import httpx
    webhook_url = f"https://{os.getenv('WEBHOOK_URL', '').strip()}/telegram-webhook"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "edited_message"]},
        )
    return {"webhook_url": webhook_url, "telegram_response": r.json()}

@app.get("/telegram-webhook/info")
async def webhook_info():
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo")
    return r.json()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = BASE_DIR / "static" / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
