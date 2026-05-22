import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.database import (
    get_or_create_user, get_credit_balance,
    deduct_credit, add_credits,
    record_transaction, mark_transaction_paid,
)
from bot.claude_client import run_analysis
from bot.paystack import create_payment_link, verify_transaction, bundle_menu_text, BUNDLES

FREE_CREDITS = int(os.getenv("FREE_CREDITS_ON_SIGNUP", 3))

WELCOME_TEXT = """
👋 *Welcome to NGX Analyst Bot!*

I deliver institutional-grade analysis for the Nigerian investment market — equities, T-Bills, FGN Bonds, and mutual funds, all powered by live data and AI.

*📈 Equities*
/analyse TICKER — market & sector analysis
/technical TICKER — chart signals (entry, SL, TP)
/fullanalysis TICKER — full institutional report
/financials TICKER — 5yr forensic breakdown
/moat TICKER — competitive moat score
/value TICKER — valuation + ₦ price target
/risk TICKER — risk matrix + stop-loss table
/growth TICKER — growth scenarios
/institutional TICKER — hedge fund view
/debate TICKER — bull vs bear verdict
/earnings TICKER — earnings scorecard
/sentiment TICKER — bullish/bearish gauge

*🏦 Fixed Income & Funds*
/tbills — NTB & OMO auction rates
/bonds — FGN Bond yield curve
/funds — mutual fund NAV comparison
/compare — fixed income vs equities decision

*🌍 Macro & Portfolio*
/macro — CBN, inflation, GDP impact
/portfolio [TICKERS] — diversification advice
/global [event] — geopolitical impact on NGX
/dividend — best yield plays (stocks + funds)

*💰 Account*
/credits — check balance
/buy — top up credits
/refer — earn credits by referring friends

You have *{credits} free credits* to start. Each analysis costs 1 credit.

Try: /technical GTCO
""".strip()


async def _send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )


async def _ensure_user(update: Update) -> dict:
    user = update.effective_user
    return get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )


async def _run_paid_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    max_tokens: int = 1500,
):
    telegram_id = update.effective_user.id
    balance = get_credit_balance(telegram_id)

    if balance < 1:
        await update.message.reply_text(
            "⚠️ *You have no credits left.*\n\nUse /buy to top up and continue.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await _send_typing(update, context)
    await update.message.reply_text(
        "🔍 _Fetching live Nigerian market data..._",
        parse_mode=ParseMode.MARKDOWN,
    )

    if not deduct_credit(telegram_id):
        await update.message.reply_text("❌ Credit deduction failed. Please try again.")
        return

    try:
        result = run_analysis(prompt, max_tokens=max_tokens)
    except Exception as e:
        add_credits(telegram_id, 1)
        await update.message.reply_text(
            f"❌ Analysis failed. Your credit has been refunded.\n\nError: {str(e)[:100]}"
        )
        return

    remaining = get_credit_balance(telegram_id)
    footer = f"\n\n_Credits remaining: {remaining}_"

    await update.message.reply_text(
        result + footer, parse_mode=ParseMode.MARKDOWN
    )


def _ticker(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.args[0].upper() if context.args else None

def _args_str(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args) if context.args else ""


# ─── Account commands ────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = await _ensure_user(update)

    if context.args:
        ref_code = context.args[0].upper()
        from bot.referral import resolve_referral_code, apply_referral, ensure_referral_code
        referrer_id = resolve_referral_code(ref_code)
        if referrer_id and referrer_id != update.effective_user.id:
            if apply_referral(update.effective_user.id, referrer_id):
                db_user = await _ensure_user(update)
                await update.message.reply_text(
                    "🎁 *Referral bonus applied!* +2 extra credits added.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 *Someone joined via your referral link!* +3 credits added.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass

    from bot.referral import ensure_referral_code
    ensure_referral_code(update.effective_user.id)

    await update.message.reply_text(
        WELCOME_TEXT.format(credits=db_user["credits"]),
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*NGX Analyst Bot — All Commands*\n\n"
        "*Equity Analysis (1 credit each)*\n"
        "/analyse /technical /fullanalysis /financials\n"
        "/moat /value /risk /growth /institutional\n"
        "/debate /earnings /sentiment /dividend\n\n"
        "*Fixed Income & Funds (1 credit each)*\n"
        "/tbills — NTB & OMO rates\n"
        "/bonds — FGN Bond yield curve\n"
        "/funds — Mutual fund NAVs\n"
        "/compare — Fixed income vs equities\n\n"
        "*Macro & Portfolio (1 credit each)*\n"
        "/macro /portfolio /global\n\n"
        "*Account (free)*\n"
        "/credits /buy /refer /start /help",
        parse_mode=ParseMode.MARKDOWN,
    )


async def credits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    balance = get_credit_balance(update.effective_user.id)
    await update.message.reply_text(
        f"💰 *Your balance: {balance} credits*\n\nEach analysis costs 1 credit.\nUse /buy to top up.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await update.message.reply_text(bundle_menu_text(), parse_mode=ParseMode.MARKDOWN)


async def _handle_bundle(update: Update, context: ContextTypes.DEFAULT_TYPE, bundle_key: str):
    await _ensure_user(update)
    user = update.effective_user
    email = f"{user.id}@ngxbot.app"
    result = create_payment_link(user.id, bundle_key, email)
    if "error" in result:
        await update.message.reply_text(f"❌ Payment error: {result['error']}")
        return
    record_transaction(user.id, result["reference"], result["amount_kobo"], result["credits"])
    bundle = BUNDLES[bundle_key]
    keyboard = [[InlineKeyboardButton("💳 Pay now", url=result["payment_url"])]]
    await update.message.reply_text(
        f"*{bundle['label']}*\n\nPay securely via Paystack. Credits added automatically after payment.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def starter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_bundle(update, context, "starter")

async def standard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_bundle(update, context, "standard")

async def power_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_bundle(update, context, "power")

async def monthly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_bundle(update, context, "monthly")


async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    from bot.referral import referral_message
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        referral_message(update.effective_user.id, bot_username),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Equity analysis commands ────────────────────────────────────────────────

async def analyse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /analyse GTCO"); return
    await _run_paid_analysis(update, context,
        f"Module 1 — Market analysis for NGX stock: {t}. Search latest sector performance, NGX index, foreign flows, and flag 2–3 opportunity stocks.")

async def technical_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /technical DANGCEM"); return
    await _run_paid_analysis(update, context,
        f"Module 2 — Technical analysis for NGX stock {t}. Assess trend, 20d/50d MA, MACD, RSI, support/resistance. Output full signal table with entry, stop-loss, breakeven, TP1, TP2.")

async def fullanalysis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /fullanalysis ZENITHBANK"); return
    await _run_paid_analysis(update, context,
        f"Module 3 — Full institutional equity report for NGX stock {t}. Cover business model, Nigerian moat, 5yr financials, risks, valuation vs peers, inflation beat verdict, bull/base/bear scenarios with ₦ price targets.",
        max_tokens=1800)

async def financials_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /financials MTNN"); return
    await _run_paid_analysis(update, context,
        f"Module 4 — Deep financial breakdown for {t}. Analyse 5yr revenue, net income, FCF, margins, FX-denominated debt (flag separately), ROE vs current CBN MPR. Deliver health verdict.")

async def moat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /moat GTCO"); return
    await _run_paid_analysis(update, context,
        f"Module 5 — Competitive moat analysis for {t} on NGX. Score 5 dimensions (1–10): brand strength in Nigeria, network effects, switching costs, cost advantages, regulatory/license moat. Stress-test vs naira devaluation. Compare to 2 sector peers.")

async def value_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /value DANGCEM"); return
    await _run_paid_analysis(update, context,
        f"Module 6 — Valuation analysis for NGX stock {t}. Calculate P/E vs sector, DCF in naira (WACC = CBN MPR + 3–5% ERP), peer multiples. Deliver ₦ price target range and inflation-adjusted return potential.")

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /risk SEPLAT"); return
    await _run_paid_analysis(update, context,
        f"Module 7 — Risk analysis for NGX stock {t}. Cover macro, regulatory, political, FX/import, competition, operational, governance risks. Output probability × impact matrix. Include stop-loss table for an equity position.")

async def growth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /growth AIRTELAFRI"); return
    await _run_paid_analysis(update, context,
        f"Module 8 — Growth potential analysis for {t} in Nigeria. Size the Nigerian TAM, assess West Africa expansion, product pipeline, tech/digital advantage (consider unbanked population and mobile penetration). Build low/mid/high growth scenarios in naira revenue.")

async def institutional_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /institutional GTCO"); return
    await _run_paid_analysis(update, context,
        f"Module 9 — Institutional investor view of NGX stock {t}. Build core thesis grounded in Nigerian macro. List catalysts with timelines (NGX earnings, CBN MPC dates). Assess NGX daily volume/liquidity. Deliver portfolio fit verdict and position sizing logic for a Nigeria-focused fund.")

async def debate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /debate ZENITHBANK"); return
    await _run_paid_analysis(update, context,
        f"Module 10 — Bull vs Bear debate on NGX stock {t}. 3 data-backed bull arguments vs 3 bear counterarguments using NGX financials and macro data. Each side rebuts the other's strongest point. Scorecard picks a winner. Final verdict: BUY / HOLD / AVOID at current ₦ price.")

async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    holdings = _args_str(context)
    prompt = (
        f"Module 11 — Portfolio diversification for NGX investor holding: {holdings}. Map to sectors, find concentration risks, suggest 3–5 additional NGX stocks, include fixed income (FGN Bonds, T-Bills) and FX hedge considerations."
        if holdings else
        "Module 11 — Give a general NGX portfolio diversification strategy for a Nigerian retail investor across equities, bonds, T-bills, and mutual funds."
    )
    await _run_paid_analysis(update, context, prompt)

async def sentiment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /sentiment ACCESSCORP"); return
    await _run_paid_analysis(update, context,
        f"Module 12 — Market sentiment analysis for NGX stock {t}. Search Nairametrics, BusinessDay, Nairaland, X/Twitter #NGX. Check institutional vs retail flows and volume spikes. Output sentiment gauge: Very Bearish → Very Bullish.")

async def earnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    t = _ticker(context)
    if not t:
        await update.message.reply_text("Usage: /earnings FBNH"); return
    await _run_paid_analysis(update, context,
        f"Module 13 — Earnings report analysis for NGX stock {t}. Find latest NGX-disclosed results. Output full earnings scorecard (Revenue, PAT, EPS, DPS, Net Margin) YoY and QoQ. Assess quality and predict price reaction.")

async def macro_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Module 14 — Nigerian economic indicators. Search and cover: CBN MPR, NBS headline + food inflation, NGN/USD official + parallel rate, GDP growth, external reserves, Brent crude price. Explain transmission to NGX equities and give sector impact map.")

async def tbills_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Module 15 — Fixed income analysis. Search DMO and CBN for latest NTB auction stop rates (91d, 182d, 364d), OMO rates, and FGN Bond yields (2yr, 5yr, 10yr, 30yr). Output full rate table. Calculate real yields vs current NBS inflation. Assess yield curve shape and recommend short vs long duration positioning based on CBN MPR outlook.")

async def bonds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Module 15 (bonds focus) — Search DMO for latest FGN Bond yields across the full curve (2yr, 5yr, 7yr, 10yr, 20yr, 30yr). Output yield table, calculate real yields vs inflation, assess curve shape (normal/flat/inverted), compare bond yields vs NGX dividend yields, and give duration recommendation.")

async def funds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Module 16 — Nigerian mutual fund analysis. Search for latest NAVs and returns from ARM Money Market, Stanbic IBTC Money Market, Coronation Money Market, FBN Quest Money Market, ARM Aggressive Growth, Stanbic IBTC Aggressive, Coronation Balanced. Output fund comparison table (type, 30-day yield, 1yr return, min investment). Compare yields vs T-bill rates and inflation. Give risk-adjusted recommendation for Conservative, Moderate, and Aggressive investor profiles.")

async def compare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Module 17 — Money market vs equity decision framework for Nigerian investors. Compare: T-Bills vs NGX Stocks | Money Market Funds vs NGX Equities | FGN Bonds vs Dividend Stocks. Build decision matrix based on: investment horizon, risk tolerance, current inflation, CBN MPR direction, NGX valuation level. Output recommended allocation for Conservative, Moderate, and Aggressive investor profiles.")

async def dividend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    await _run_paid_analysis(update, context,
        "Best yield plays across the full Nigerian investment universe. Search: top NGX dividend stocks (yield, payout history, cover ratio), top money market fund rates, current T-bill 364-day rate. Check if each yield beats current NBS inflation. Output ranked yield comparison table across all three asset classes. Recommend by investor type.")

async def global_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ensure_user(update)
    event = _args_str(context) or "current global market conditions"
    await _run_paid_analysis(update, context,
        f"Module 18 — Impact of {event} on NGX and Nigerian investments. Cover oil price, FX, remittances, trade impact. Flag vulnerable NGX sectors and defensive plays. Suggest portfolio hedges for a Nigerian investor (USD assets, gold, Eurobonds, T-bills).")
