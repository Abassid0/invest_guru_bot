"""
Telegram Command Handlers — all bot logic consolidated here.
Called from main.py's /telegram-webhook endpoint.
"""
import os
import httpx
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text as sql_text

from database.models import (
    create_database_engine, get_session,
    Company, StockPrice, MacroIndicator, InflationData,
)
from database.bot_db import (
    get_or_create_user, get_credit_balance, deduct_credit,
    add_credits, get_user_stats, PLANS,
    save_conversation, get_conversation_history,
    add_watchlist, get_watchlist, remove_watchlist,
    save_feedback,
)


# ── Live data context builder ─────────────────────────────────────────────────

def _build_data_context(engine, ticker: str) -> str:
    """Query DB for live prices, price history, macro, and performance for a ticker.
    Returns a formatted string to inject into the Claude prompt."""
    session = get_session(engine)
    parts = []
    try:
        # Current macro snapshot
        macro = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        inflation = session.query(InflationData).order_by(InflationData.date.desc()).first()
        if macro:
            parts.append(
                "=== CURRENT MACRO DATA ===\n"
                f"Date: {macro.date}\n"
                f"CBN MPR: {float(macro.mpr):.2f}%\n"
                f"USD/NGN Official: {float(macro.usd_ngn_official):,.0f}\n"
                f"USD/NGN Parallel: {float(macro.usd_ngn_parallel):,.0f}\n"
                f"91-day T-bill: {float(macro.treasury_bill_91d):.2f}%\n"
                f"364-day T-bill: {float(macro.treasury_bill_364d):.2f}%\n"
                f"Brent Crude: ${float(macro.brent_crude_usd):.2f}"
            )
        if inflation:
            parts.append(
                f"Headline Inflation: {float(inflation.headline_cpi):.2f}%\n"
                f"Food Inflation: {float(inflation.food_inflation):.2f}%"
            )

        if not ticker or ticker == "NGX MARKET":
            # Market-wide: show all stock prices
            rows = session.execute(sql_text(
                "SELECT c.ticker, c.name, c.sector, sp.close, sp.change_percent, sp.date "
                "FROM companies c "
                "JOIN stock_prices sp ON sp.company_id = c.id "
                "WHERE c.is_active = true "
                "AND sp.date = (SELECT MAX(date) FROM stock_prices) "
                "ORDER BY c.sector, c.ticker"
            )).fetchall()
            if rows:
                lines = ["=== ALL NGX STOCK PRICES (latest) ==="]
                for r in rows:
                    chg = f"{float(r[4]):+.2f}%" if r[4] else ""
                    lines.append(f"{r[0]:15s} N{float(r[3]):>10,.2f}  {chg:>8s}  {r[2]}")
                parts.append("\n".join(lines))
            return "\n\n".join(parts)

        # Single stock context
        company = session.query(Company).filter_by(ticker=ticker, is_active=True).first()
        if not company:
            parts.append(f"NOTE: Ticker {ticker} not found in our database.")
            return "\n\n".join(parts)

        parts.append(
            f"=== STOCK: {company.ticker} — {company.name} ===\n"
            f"Sector: {company.sector}\n"
            f"FX Revenue: {'Yes' if company.has_fx_revenue else 'No'}\n"
            f"Inflation Beater: {'Yes' if company.is_inflation_beater else 'No'}"
        )

        # Latest price + recent price history (up to 30 data points)
        prices = session.query(StockPrice).filter_by(
            company_id=company.id
        ).order_by(StockPrice.date.desc()).limit(30).all()

        if prices:
            latest = prices[0]
            parts.append(
                f"=== CURRENT PRICE ===\n"
                f"Price: N{float(latest.close):,.2f}\n"
                f"Date: {latest.date}\n"
                f"Change: {float(latest.change_percent or 0):+.2f}%\n"
                f"Volume: {latest.volume or 0:,}\n"
                f"Source: {latest.source or 'N/A'}"
            )

            if len(prices) > 1:
                lines = ["=== PRICE HISTORY (recent) ==="]
                for p in prices[:15]:
                    lines.append(f"  {p.date}  N{float(p.close):>10,.2f}  {float(p.change_percent or 0):+.2f}%  vol={p.volume or 0:>10,}")
                if len(prices) > 1:
                    oldest = prices[-1]
                    period_return = ((float(latest.close) / float(oldest.close)) - 1) * 100
                    lines.append(f"\nReturn over this period: {period_return:+.1f}%")
                parts.append("\n".join(lines))

        # Inflation performance
        perf = session.execute(sql_text(
            "SELECT return_1yr, return_3yr, return_5yr, "
            "excess_return_1yr, excess_return_3yr, excess_return_5yr, "
            "beats_inflation_1yr, beats_inflation_3yr, beats_inflation_all "
            "FROM inflation_performance WHERE company_id = :cid"
        ), {"cid": company.id}).fetchone()
        if perf:
            def _fmt(val, fmt=".1f"):
                return f"{float(val):{fmt}}" if val is not None else "N/A"
            def _fmtp(val):
                return f"{float(val):+.1f}" if val is not None else "N/A"
            def _yn(val):
                return "Yes" if val else "No"
            parts.append(
                "=== INFLATION PERFORMANCE ===\n"
                f"1yr Return: {_fmt(perf[0])}% | Excess vs Inflation: {_fmtp(perf[3])}% | Beats: {_yn(perf[6])}\n"
                f"3yr Return: {_fmt(perf[1])}% | Excess vs Inflation: {_fmtp(perf[4])}% | Beats: {_yn(perf[7])}\n"
                f"5yr Return: {_fmt(perf[2])}% | Excess vs Inflation: {_fmtp(perf[5])}% | Beats: {_yn(perf[8])}"
            )

        # Peer comparison (same sector)
        peers = session.execute(sql_text(
            "SELECT c.ticker, sp.close, sp.change_percent "
            "FROM companies c "
            "JOIN stock_prices sp ON sp.company_id = c.id "
            "WHERE c.sector = :sector AND c.is_active = true AND c.ticker != :ticker "
            "AND sp.date = (SELECT MAX(date) FROM stock_prices WHERE company_id = c.id) "
            "ORDER BY sp.close DESC"
        ), {"sector": company.sector, "ticker": ticker}).fetchall()
        if peers:
            lines = [f"=== SECTOR PEERS ({company.sector}) ==="]
            for p in peers:
                chg = f"{float(p[2]):+.2f}%" if p[2] else ""
                lines.append(f"  {p[0]:15s}  N{float(p[1]):>10,.2f}  {chg}")
            parts.append("\n".join(lines))

    finally:
        session.close()

    return "\n\n".join(parts)


def _build_market_context(engine) -> str:
    """Build market-wide data context for commands that don't target a specific ticker."""
    return _build_data_context(engine, ticker=None)


# ── Telegram helpers ──────────────────────────────────────────────────────────

async def _tg_send(chat_id: int, text: str, telegram_api: str) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{telegram_api}/sendMessage", json=payload)
    return r.json()


async def _tg_send_typing(chat_id: int, telegram_api: str):
    payload = {"chat_id": chat_id, "action": "typing"}
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{telegram_api}/sendChatAction", json=payload)


# ── Module-N command prompts (detailed, for better Claude output) ─────────────

COMMAND_PROMPTS = {
    "/analyse": (
        "Module 1 — Market analysis for NGX stock: {arg}. Search latest sector "
        "performance, NGX index, foreign flows, and flag 2-3 opportunity stocks."
    ),
    "/technical": (
        "Module 2 — Technical analysis for NGX stock {arg}. Assess trend, "
        "20d/50d MA, MACD, RSI, support/resistance. Output full signal table "
        "with entry, stop-loss, breakeven, TP1, TP2."
    ),
    "/fullanalysis": (
        "Module 3 — Full institutional equity report for NGX stock {arg}. "
        "Cover business model, Nigerian moat, 5yr financials, risks, valuation "
        "vs peers, inflation beat verdict, bull/base/bear scenarios with price targets."
    ),
    "/financials": (
        "Module 4 — Deep financial breakdown for {arg}. Analyse 5yr revenue, "
        "net income, FCF, margins, FX-denominated debt (flag separately), "
        "ROE vs current CBN MPR. Deliver health verdict."
    ),
    "/moat": (
        "Module 5 — Competitive moat analysis for {arg} on NGX. Score 5 dimensions "
        "(1-10): brand strength in Nigeria, network effects, switching costs, cost "
        "advantages, regulatory/license moat. Stress-test vs naira devaluation. "
        "Compare to 2 sector peers."
    ),
    "/value": (
        "Module 6 — Valuation analysis for NGX stock {arg}. Calculate P/E vs sector, "
        "DCF in naira (WACC = CBN MPR + 3-5% ERP), peer multiples. Deliver price "
        "target range and inflation-adjusted return potential."
    ),
    "/risk": (
        "Module 7 — Risk analysis for NGX stock {arg}. Cover macro, regulatory, "
        "political, FX/import, competition, operational, governance risks. Output "
        "probability x impact matrix. Include stop-loss table for an equity position."
    ),
    "/growth": (
        "Module 8 — Growth potential analysis for {arg} in Nigeria. Size the Nigerian "
        "TAM, assess West Africa expansion, product pipeline, tech/digital advantage "
        "(consider unbanked population and mobile penetration). Build low/mid/high "
        "growth scenarios in naira revenue."
    ),
    "/institutional": (
        "Module 9 — Institutional investor view of NGX stock {arg}. Build core thesis "
        "grounded in Nigerian macro. List catalysts with timelines (NGX earnings, CBN "
        "MPC dates). Assess NGX daily volume/liquidity. Deliver portfolio fit verdict "
        "and position sizing logic for a Nigeria-focused fund."
    ),
    "/debate": (
        "Module 10 — Bull vs Bear debate on NGX stock {arg}. 3 data-backed bull "
        "arguments vs 3 bear counterarguments using NGX financials and macro data. "
        "Each side rebuts the other's strongest point. Scorecard picks a winner. "
        "Final verdict: BUY / HOLD / AVOID at current price."
    ),
    "/earnings": (
        "Module 13 — Earnings report analysis for NGX stock {arg}. Find latest "
        "NGX-disclosed results. Output full earnings scorecard (Revenue, PAT, EPS, "
        "DPS, Net Margin) YoY and QoQ. Assess quality and predict price reaction."
    ),
    "/sentiment": (
        "Module 12 — Market sentiment analysis for NGX stock {arg}. Search Nairametrics, "
        "BusinessDay, Nairaland, X/Twitter #NGX. Check institutional vs retail flows "
        "and volume spikes. Output sentiment gauge: Very Bearish to Very Bullish."
    ),
    "/tbills": (
        "Module 15 — Fixed income analysis. Search DMO and CBN for latest NTB auction "
        "stop rates (91d, 182d, 364d), OMO rates, and FGN Bond yields (2yr, 5yr, 10yr, 30yr). "
        "Output full rate table. Calculate real yields vs current NBS inflation. Assess yield "
        "curve shape and recommend short vs long duration positioning based on CBN MPR outlook."
    ),
    "/bonds": (
        "Module 15 (bonds focus) — Search DMO for latest FGN Bond yields across the "
        "full curve (2yr, 5yr, 7yr, 10yr, 20yr, 30yr). Output yield table, calculate "
        "real yields vs inflation, assess curve shape, compare bond yields vs NGX "
        "dividend yields, and give duration recommendation."
    ),
    "/funds": (
        "Module 16 — Nigerian mutual fund analysis. Search for latest NAVs and returns "
        "from ARM Money Market, Stanbic IBTC Money Market, Coronation Money Market, "
        "FBN Quest Money Market, ARM Aggressive Growth, Stanbic IBTC Aggressive, "
        "Coronation Balanced. Output fund comparison table. Compare yields vs T-bill "
        "rates and inflation. Give risk-adjusted recommendation."
    ),
    "/compare": (
        "Module 17 — Money market vs equity decision framework for Nigerian investors. "
        "Compare: T-Bills vs NGX Stocks | Money Market Funds vs NGX Equities | "
        "FGN Bonds vs Dividend Stocks. Build decision matrix based on: investment horizon, "
        "risk tolerance, current inflation, CBN MPR direction, NGX valuation level."
    ),
    "/dividend": (
        "Best yield plays across the full Nigerian investment universe. Search: top NGX "
        "dividend stocks (yield, payout history, cover ratio), top money market fund rates, "
        "current T-bill 364-day rate. Check if each yield beats current NBS inflation. "
        "Output ranked yield comparison table across all three asset classes."
    ),
    "/portfolio": (
        "Module 11 — Portfolio diversification for NGX investor holding: {arg}. Map to "
        "sectors, find concentration risks, suggest 3-5 additional NGX stocks, include "
        "fixed income (FGN Bonds, T-Bills) and FX hedge considerations."
    ),
    "/global": (
        "Module 18 — Impact of {arg} on NGX and Nigerian investments. Cover oil price, "
        "FX, remittances, trade impact. Flag vulnerable NGX sectors and defensive plays. "
        "Suggest portfolio hedges for a Nigerian investor."
    ),
    "/devaluation": (
        "Which NGX stocks protect my money when the naira falls? Rank stocks by foreign "
        "currency revenue exposure (USD, EUR, GBP earnings). Identify companies that "
        "historically perform well during naira depreciation. Focus on: oil exporters, "
        "telecoms with USD billing, agro-commodity exporters, cement with export capacity. "
        "Give practical advice for a Nigerian investor worried about naira losing value."
    ),
    "/fxhedge": (
        "Which NGX stocks protect my money when the naira falls? Rank stocks by foreign "
        "currency revenue exposure (USD, EUR, GBP earnings). Identify companies that "
        "historically perform well during naira depreciation. Give practical advice."
    ),
}

HELP_TEXT = (
    "NGX Investment Intelligence Bot\n"
    "Credits remaining: {credits}\n\n"
    "EQUITIES (1 credit each)\n"
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
    "FIXED INCOME & FUNDS (1 credit each)\n"
    "/tbills - NTB & OMO auction rates\n"
    "/bonds - FGN Bond yield curve\n"
    "/funds - mutual fund NAV comparison\n"
    "/compare - fixed income vs equities\n\n"
    "MACRO & PORTFOLIO (1 credit each)\n"
    "/macro - CBN, inflation, FX rates\n"
    "/portfolio GTCO DANGCEM - diversification\n"
    "/global EVENT - geopolitical impact on NGX\n"
    "/dividend - best yield plays\n"
    "/devaluation - naira hedge stocks\n\n"
    "BACKTESTING\n"
    "/backtest - test inflation strategy (3 years)\n"
    "/backtest 5years - test last 5 years\n"
    "/backtest hold GTCO DANGCEM - buy-and-hold test\n"
    "/backtest compare - compare all strategies\n"
    "/backtest devaluation - test FX hedge strategy\n\n"
    "WATCHLIST & ALERTS (free)\n"
    "/watch TICKER PRICE - set price alert\n"
    "/watchlist - view your alerts\n"
    "/unwatch TICKER - remove alert\n\n"
    "ACCOUNT & FEEDBACK (free)\n"
    "/credits - check your credit balance\n"
    "/buy - top up credits\n"
    "/refer - get your referral link\n"
    "/rate 5 Great! - rate your last analysis\n\n"
    "Each analysis costs 1 credit. /buy to get more."
)


# ── Main dispatcher ──────────────────────────────────────────────────────────

async def handle_telegram_message(data: dict, engine, telegram_api: str) -> dict:
    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    tg_user = message.get("from", {})
    text = (message.get("text") or "").strip()
    user_name = tg_user.get("first_name", "Investor")
    username = tg_user.get("username", "")

    if not text:
        return {"ok": True}

    try:
        return await _dispatch(data, engine, telegram_api, chat_id, tg_user, text, user_name, username)
    except Exception as e:
        try:
            await _tg_send(chat_id, f"Something went wrong. Please try again.\n\nError: {str(e)[:150]}", telegram_api)
        except Exception:
            pass
        return {"ok": True}


async def _dispatch(data: dict, engine, telegram_api: str, chat_id: int,
                    tg_user: dict, text: str, user_name: str, username: str) -> dict:

    # ── Ensure user exists ────────────────────────────────────────────────
    session = get_session(engine)
    try:
        ref_code = None
        if text.startswith("/start ") or text.startswith("/join "):
            parts = text.split(maxsplit=1)
            ref_code = parts[1].strip() if len(parts) > 1 else None

        user = get_or_create_user(
            session, chat_id, username=username,
            first_name=user_name, referral_code_used=ref_code
        )
        credits_left = user.credits
    finally:
        session.close()

    # ── Free commands (no credit cost) ────────────────────────────────────

    if text.startswith("/start") or text.startswith("/help") or text.startswith("/join"):
        greeting = ""
        if not text.startswith("/help"):
            greeting = (
                f"Welcome {user_name}!\n"
                f"You have {credits_left} free {'credit' if credits_left == 1 else 'credits'} to start.\n\n"
            )
        await _tg_send(chat_id, greeting + HELP_TEXT.format(credits=credits_left), telegram_api)
        return {"ok": True}

    if text.startswith("/credits"):
        session = get_session(engine)
        try:
            stats = get_user_stats(session, chat_id)
        finally:
            session.close()
        await _tg_send(chat_id,
            f"Your Account\n\n"
            f"Credits: {stats.get('credits', 0)}\n"
            f"Total referrals: {stats.get('total_referrals', 0)}\n"
            f"Paid referrals: {stats.get('paid_referrals', 0)}\n"
            f"Total spent: N{stats.get('total_spent_ngn', 0):,.0f}\n"
            f"Member since: {stats.get('member_since', 'N/A')}\n\n"
            f"Use /buy to top up or /refer to earn free credits.",
            telegram_api
        )
        return {"ok": True}

    if text.startswith("/buy"):
        from bot.paystack import handle_buy_command
        await handle_buy_command(text, chat_id, username, engine, telegram_api)
        return {"ok": True}

    if text.startswith("/refer"):
        from bot.referral import referral_message
        session = get_session(engine)
        try:
            msg = referral_message(session, chat_id, "Naija_Guru_Bot")
        finally:
            session.close()
        await _tg_send(chat_id, msg, telegram_api)
        return {"ok": True}

    # ── Watchlist commands (free) ─────────────────────────────────────────

    if text.startswith("/watch ") and not text.startswith("/watchlist"):
        return await _handle_watch(text, chat_id, engine, telegram_api)

    if text.startswith("/watchlist"):
        return await _handle_watchlist(chat_id, engine, telegram_api)

    if text.startswith("/unwatch"):
        return await _handle_unwatch(text, chat_id, engine, telegram_api)

    # ── Feedback commands (free) ──────────────────────────────────────────

    if text.startswith("/rate") or text.startswith("/feedback"):
        return await _handle_feedback(text, chat_id, engine, telegram_api)

    # ── Macro (served from DB, no Claude needed) ──────────────────────────

    if text.startswith("/macro"):
        return await _handle_macro(chat_id, engine, telegram_api)

    # ── Backtest commands ─────────────────────────────────────────────────

    if text.startswith("/backtest"):
        return await _handle_backtest(text, chat_id, engine, telegram_api)

    # ── Paid analysis commands (1 credit each) ────────────────────────────

    cmd = None
    claude_prompt = text
    analysis_ticker = None
    for command, template in COMMAND_PROMPTS.items():
        if text.lower().startswith(command):
            cmd = command
            arg = text[len(command):].strip().upper() or "NGX market"
            claude_prompt = template.format(arg=arg)
            analysis_ticker = arg if arg != "NGX market" else None
            break

    # Credit gate
    session = get_session(engine)
    try:
        has_credit = deduct_credit(session, chat_id)
    finally:
        session.close()

    if not has_credit:
        await _tg_send(chat_id,
            f"You have 0 credits remaining.\n\n"
            f"Top up to continue:\n"
            f"/buy per_view   - N100 for 1 analysis\n"
            f"/buy bundle_5   - N400 for 5 analyses\n"
            f"/buy bundle_10  - N700 for 10 analyses\n"
            f"/buy monthly_basic - N2,000 for 50/month\n\n"
            f"Or earn free credits: /refer",
            telegram_api
        )
        return {"ok": True}

    # Send typing indicator
    await _tg_send_typing(chat_id, telegram_api)

    # Inject live data from our DB into the prompt
    try:
        if analysis_ticker:
            data_context = _build_data_context(engine, analysis_ticker)
        else:
            data_context = _build_market_context(engine)
        claude_prompt = (
            f"{claude_prompt}\n\n"
            f"--- LIVE DATA FROM OUR DATABASE (use this for your analysis) ---\n"
            f"{data_context}\n"
            f"--- END LIVE DATA ---\n\n"
            f"IMPORTANT: Use the data above to provide specific numbers, prices, "
            f"and analysis. Never say you don't have access to data. "
            f"You have real-time NGX data. Deliver the analysis."
        )
    except Exception:
        pass

    # Fetch conversation history for context
    session = get_session(engine)
    try:
        history = get_conversation_history(session, chat_id, limit=5)
        save_conversation(session, chat_id, "user", text, command=cmd)
    finally:
        session.close()

    # Call Claude with conversation context + live data
    try:
        from claude_client import run_analysis
        reply = run_analysis(
            claude_prompt,
            max_tokens=1200,
            conversation_history=history,
            mode="telegram",
        )

        # Save assistant response
        session = get_session(engine)
        try:
            save_conversation(session, chat_id, "assistant", reply)
            remaining = get_credit_balance(session, chat_id)
        finally:
            session.close()

        footer = f"\n\n[{remaining} credit(s) left - /buy to top up]\nWas this helpful? /rate 5 or /rate 1"
        full_msg = reply + footer

        # Telegram message limit is 4096 chars; split if needed
        if len(full_msg) <= 4096:
            await _tg_send(chat_id, full_msg, telegram_api)
        else:
            # Send analysis in chunks, footer on last chunk
            chunks = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    chunk += footer
                await _tg_send(chat_id, chunk, telegram_api)
    except Exception as e:
        # Refund credit on error
        session = get_session(engine)
        try:
            add_credits(session, chat_id, 1)
        finally:
            session.close()
        await _tg_send(chat_id, f"Analysis unavailable: {str(e)[:200]}", telegram_api)

    return {"ok": True}


# ── Sub-handlers ──────────────────────────────────────────────────────────────

async def _handle_watch(text: str, chat_id: int, engine, telegram_api: str) -> dict:
    parts = text.split()
    if len(parts) < 3:
        await _tg_send(chat_id,
            "Usage: /watch TICKER PRICE\n"
            "Example: /watch GTCO 45.00\n"
            "I'll notify you when the price crosses that level.",
            telegram_api
        )
        return {"ok": True}

    ticker = parts[1].upper()
    try:
        price = float(parts[2])
    except ValueError:
        await _tg_send(chat_id, "Price must be a number. Example: /watch GTCO 45.00", telegram_api)
        return {"ok": True}

    session = get_session(engine)
    try:
        company = session.query(Company).filter_by(ticker=ticker, is_active=True).first()
        if not company:
            await _tg_send(chat_id, f"Stock {ticker} not found. Check the ticker and try again.", telegram_api)
            return {"ok": True}
        add_watchlist(session, chat_id, ticker, above=price)
    finally:
        session.close()

    await _tg_send(chat_id,
        f"Alert set! I'll notify you when {ticker} crosses N{price:,.2f}\n"
        f"Use /watchlist to see all your alerts.",
        telegram_api
    )
    return {"ok": True}


async def _handle_watchlist(chat_id: int, engine, telegram_api: str) -> dict:
    session = get_session(engine)
    try:
        watches = get_watchlist(session, chat_id)
    finally:
        session.close()

    if not watches:
        await _tg_send(chat_id,
            "You have no active price alerts.\n"
            "Set one: /watch GTCO 45.00",
            telegram_api
        )
        return {"ok": True}

    lines = ["Your Price Alerts\n"]
    for i, w in enumerate(watches, 1):
        direction = ""
        if w["above"]:
            direction = f"above N{w['above']:,.2f}"
        if w["below"]:
            direction += f"{' / ' if direction else ''}below N{w['below']:,.2f}"
        lines.append(f"{i}. {w['ticker']} - alert {direction}")
    lines.append(f"\nRemove: /unwatch TICKER")
    await _tg_send(chat_id, "\n".join(lines), telegram_api)
    return {"ok": True}


async def _handle_unwatch(text: str, chat_id: int, engine, telegram_api: str) -> dict:
    parts = text.split()
    if len(parts) < 2:
        await _tg_send(chat_id, "Usage: /unwatch GTCO", telegram_api)
        return {"ok": True}

    ticker = parts[1].upper()
    session = get_session(engine)
    try:
        removed = remove_watchlist(session, chat_id, ticker)
    finally:
        session.close()

    if removed:
        await _tg_send(chat_id, f"Alert for {ticker} removed.", telegram_api)
    else:
        await _tg_send(chat_id, f"No active alert found for {ticker}.", telegram_api)
    return {"ok": True}


async def _handle_feedback(text: str, chat_id: int, engine, telegram_api: str) -> dict:
    if text.startswith("/feedback"):
        await _tg_send(chat_id,
            "Rate your last analysis (1-5):\n\n"
            "/rate 5 Excellent, very helpful!\n"
            "/rate 4 Good analysis\n"
            "/rate 3 Average, could be better\n"
            "/rate 2 Not very useful\n"
            "/rate 1 Poor, needs improvement\n\n"
            "Add a comment after the number if you want.",
            telegram_api
        )
        return {"ok": True}

    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await _tg_send(chat_id, "Usage: /rate 5 Great analysis!", telegram_api)
        return {"ok": True}

    try:
        rating = int(parts[1])
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        await _tg_send(chat_id, "Rating must be a number 1-5. Example: /rate 4 Good!", telegram_api)
        return {"ok": True}

    comment = parts[2] if len(parts) > 2 else None

    session = get_session(engine)
    try:
        save_feedback(session, chat_id, command="last_analysis", rating=rating, comment=comment)
    finally:
        session.close()

    responses = {
        5: "Thank you! Glad it was helpful.",
        4: "Thanks for the feedback! We're glad it was useful.",
        3: "Thank you. We'll work on making analyses more useful.",
        2: "Noted. We appreciate your honest feedback.",
        1: "Sorry it wasn't helpful. Your feedback helps us improve.",
    }
    await _tg_send(chat_id, responses.get(rating, "Thanks for your feedback!"), telegram_api)
    return {"ok": True}


async def _handle_macro(chat_id: int, engine, telegram_api: str) -> dict:
    session = get_session(engine)
    try:
        macro = session.query(MacroIndicator).order_by(MacroIndicator.date.desc()).first()
        inflation = session.query(InflationData).order_by(InflationData.date.desc()).first()
    finally:
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
            "Use /compare to see how T-bills stack up vs equities.",
            telegram_api
        )
    else:
        await _tg_send(chat_id, "Macro data not available yet. Contact admin.", telegram_api)
    return {"ok": True}


async def _handle_backtest(text: str, chat_id: int, engine, telegram_api: str) -> dict:
    args = text[len("/backtest"):].strip().lower()
    base_url = f"https://{os.getenv('WEBHOOK_URL', '').strip()}"

    try:
        async with httpx.AsyncClient(timeout=60) as client:

            if args == "compare":
                r = await client.get(f"{base_url}/api/backtest/compare")
                data = r.json()
                lines = ["Strategy Comparison\n"]
                for key, strategy in data.items():
                    if key == "comparison_summary" or "metrics" not in strategy:
                        continue
                    m = strategy["metrics"]
                    lines.append(
                        f"{strategy.get('strategy_name', key)}\n"
                        f"  Total Return: {m.get('total_return', 0):.1f}%\n"
                        f"  Annual Return: {m.get('annual_return', 0):.1f}%\n"
                        f"  Sharpe Ratio: {m.get('sharpe_ratio', 0):.2f}\n"
                        f"  Max Drawdown: {m.get('max_drawdown', 0):.1f}%\n"
                    )
                await _tg_send(chat_id, "\n".join(lines), telegram_api)
                return {"ok": True}

            if args.startswith("hold"):
                tickers = [t.strip().upper() for t in args[4:].split() if t.strip()]
                if not tickers:
                    await _tg_send(chat_id, "Usage: /backtest hold GTCO DANGCEM ZENITHBANK", telegram_api)
                    return {"ok": True}
                r = await client.post(f"{base_url}/api/backtest/buy-hold", json={
                    "tickers": tickers,
                    "initial_capital": 1_000_000,
                })
                result = r.json()

            elif args == "devaluation":
                r = await client.post(f"{base_url}/api/backtest/devaluation-strategy", json={
                    "initial_capital": 1_000_000,
                })
                result = r.json()

            else:
                payload = {"initial_capital": 1_000_000}
                if args == "5years":
                    start = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
                    payload["start_date"] = start
                elif len(args.split()) == 2:
                    parts = args.split()
                    payload["start_date"] = parts[0]
                    payload["end_date"] = parts[1]
                r = await client.post(f"{base_url}/api/backtest/inflation-strategy", json=payload)
                result = r.json()

            if "metrics" in result:
                m = result["metrics"]
                name = result.get("strategy_name", "Backtest")
                period = result.get("period", {})
                msg = (
                    f"Backtest: {name}\n"
                    f"Period: {period.get('start', '')[:7]} to {period.get('end', '')[:7]}\n\n"
                    f"Total Return:   {m.get('total_return', 0):+.1f}%\n"
                    f"Annual Return:  {m.get('annual_return', 0):+.1f}%\n"
                    f"Sharpe Ratio:   {m.get('sharpe_ratio', 0):.2f}\n"
                    f"Max Drawdown:   {m.get('max_drawdown', 0):.1f}%\n"
                    f"Win Rate:       {m.get('win_rate', 0):.0f}%\n"
                    f"Total Trades:   {m.get('num_trades', 0)}\n"
                    f"Final Value:    N{m.get('final_value', 0):,.0f}\n"
                    f"P&L:            N{m.get('total_profit_loss', 0):+,.0f}\n\n"
                    f"(Started with N1,000,000)\n"
                    f"Type /backtest compare to see how this compares."
                )
                await _tg_send(chat_id, msg, telegram_api)
            elif "error" in result:
                await _tg_send(chat_id,
                    f"Backtest: {result['error']}\n\n"
                    f"Note: backtesting requires historical price data. "
                    f"Try /analyse TICKER for live analysis.",
                    telegram_api
                )
            else:
                await _tg_send(chat_id,
                    "Backtest returned no results. Try /analyse TICKER instead.",
                    telegram_api
                )
    except Exception as e:
        await _tg_send(chat_id, f"Backtest error: {str(e)[:200]}", telegram_api)

    return {"ok": True}
