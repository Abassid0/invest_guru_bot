import os
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Header
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler
from dotenv import load_dotenv

from handlers import (
    start, help_cmd, credits_cmd, buy_cmd, refer_cmd,
    starter_cmd, standard_cmd, power_cmd, monthly_cmd,
    # Equities
    analyse_cmd, technical_cmd, fullanalysis_cmd, financials_cmd,
    moat_cmd, value_cmd, risk_cmd, growth_cmd, institutional_cmd,
    debate_cmd, portfolio_cmd, sentiment_cmd, earnings_cmd,
    # Fixed income & funds
    macro_cmd, tbills_cmd, bonds_cmd, funds_cmd, compare_cmd,
    # Mixed
    dividend_cmd, global_cmd,
)

from database import add_credits, mark_transaction_paid
from paystack import verify_webhook_signature, verify_transaction
from scheduler import create_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

tg_app    = Application.builder().token(BOT_TOKEN).build()
scheduler = create_scheduler()


def register_handlers():
    h = tg_app.add_handler
    h(CommandHandler("start",          start))
    h(CommandHandler("help",           help_cmd))
    h(CommandHandler("credits",        credits_cmd))
    h(CommandHandler("buy",            buy_cmd))
    h(CommandHandler("refer",          refer_cmd))
    h(CommandHandler("starter",        starter_cmd))
    h(CommandHandler("standard",       standard_cmd))
    h(CommandHandler("power",          power_cmd))
    h(CommandHandler("monthly",        monthly_cmd))
    # Equity
    h(CommandHandler("analyse",        analyse_cmd))
    h(CommandHandler("analyze",        analyse_cmd))
    h(CommandHandler("technical",      technical_cmd))
    h(CommandHandler("fullanalysis",   fullanalysis_cmd))
    h(CommandHandler("financials",     financials_cmd))
    h(CommandHandler("moat",           moat_cmd))
    h(CommandHandler("value",          value_cmd))
    h(CommandHandler("risk",           risk_cmd))
    h(CommandHandler("growth",         growth_cmd))
    h(CommandHandler("institutional",  institutional_cmd))
    h(CommandHandler("debate",         debate_cmd))
    h(CommandHandler("portfolio",      portfolio_cmd))
    h(CommandHandler("sentiment",      sentiment_cmd))
    h(CommandHandler("earnings",       earnings_cmd))
    # Fixed income & funds
    h(CommandHandler("macro",          macro_cmd))
    h(CommandHandler("tbills",         tbills_cmd))
    h(CommandHandler("bonds",          bonds_cmd))
    h(CommandHandler("funds",          funds_cmd))
    h(CommandHandler("compare",        compare_cmd))
    # Mixed
    h(CommandHandler("dividend",       dividend_cmd))
    h(CommandHandler("global",         global_cmd))


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_handlers()
    await tg_app.initialize()
    webhook_endpoint = f"{WEBHOOK_URL}/telegram/webhook"
    await tg_app.bot.set_webhook(url=webhook_endpoint)
    logger.info(f"Webhook registered: {webhook_endpoint}")
    scheduler.start()
    logger.info("Scheduler started — daily signals active")
    yield
    scheduler.shutdown(wait=False)
    await tg_app.bot.delete_webhook()
    await tg_app.shutdown()


app = FastAPI(title="NGX Analyst Bot v2", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/")
async def health():
    return {"status": "ok", "version": "2.0", "bot": "NGX Analyst Bot"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    body = await request.json()
    update = Update.de_json(body, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}


@app.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(None),
):
    body = await request.body()
    if not verify_webhook_signature(body, x_paystack_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(body)
    if event.get("event") == "charge.success":
        reference = event["data"]["reference"]
        txn = mark_transaction_paid(reference)
        if txn and txn.get("status") != "paid":
            telegram_id = txn["telegram_id"]
            credits     = txn["credits"]
            add_credits(telegram_id, credits)
            try:
                bot = Bot(token=BOT_TOKEN)
                await bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"✅ *Payment confirmed!*\n\n"
                        f"*{credits} credits* added to your account.\n\n"
                        f"Try: /technical GTCO or /tbills"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Notify failed for {telegram_id}: {e}")

    return {"status": "ok"}


@app.get("/paystack/callback")
async def paystack_callback(reference: str):
    result = verify_transaction(reference)
    if result["success"]:
        return {"message": "Payment successful! Return to Telegram.", "credits": result["credits"]}
    return {"message": "Payment could not be verified. Contact support."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
