"""
Paystack Payment Integration — extracted from main.py.
Handles payment link creation, webhook verification, and buy command.
"""
import os
import hmac
import hashlib
import json

import httpx

from database.models import get_session
from database.bot_db import add_credits, get_credit_balance, PLANS


PAYSTACK_SECRET = (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()


async def _tg_send(chat_id: int, text: str, telegram_api: str) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{telegram_api}/sendMessage", json=payload)
    return r.json()


async def create_payment_link(chat_id: int, plan_key: str, username: str = "") -> dict:
    if not PAYSTACK_SECRET:
        return {"error": "Payment not configured"}

    plan = PLANS.get(plan_key)
    if not plan:
        return {"error": f"Unknown plan: {plan_key}"}

    email = f"user{chat_id}@ngxbot.app"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.paystack.co/transaction/initialize",
            headers={
                "Authorization": f"Bearer {PAYSTACK_SECRET}",
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "amount": plan["price_kobo"],
                "currency": "NGN",
                "metadata": {
                    "telegram_id": str(chat_id),
                    "plan": plan_key,
                    "username": username or str(chat_id),
                    "custom_fields": [
                        {"display_name": "Plan", "variable_name": "plan", "value": plan["name"]},
                        {"display_name": "Telegram ID", "variable_name": "telegram_id", "value": str(chat_id)},
                    ],
                },
                "callback_url": f"https://{WEBHOOK_URL}/payment-success",
            },
        )
    resp = r.json()
    if resp.get("status") and resp.get("data", {}).get("authorization_url"):
        return {"url": resp["data"]["authorization_url"], "plan": plan}
    return {"error": resp.get("message", "Unknown error")}


async def handle_buy_command(text: str, chat_id: int, username: str,
                             engine, telegram_api: str):
    parts = text.split()
    chosen_plan = parts[1].lower() if len(parts) > 1 else None

    if chosen_plan and chosen_plan in PLANS:
        plan = PLANS[chosen_plan]
        try:
            result = await create_payment_link(chat_id, chosen_plan, username)
            if "error" in result:
                await _tg_send(chat_id, f"Payment error: {result['error']}", telegram_api)
                return

            await _tg_send(chat_id,
                f"Payment Link Ready!\n\n"
                f"Plan: {plan['name']}\n"
                f"Amount: N{plan['price_ngn']:,}\n"
                f"Credits: {plan['credits']}\n\n"
                f"Pay here:\n{result['url']}\n\n"
                f"Credits will be added automatically after payment.\n"
                f"Link expires in 1 hour.",
                telegram_api,
            )
        except Exception as e:
            await _tg_send(chat_id, f"Payment error: {str(e)[:150]}", telegram_api)
    else:
        lines = ["Choose a plan:\n"]
        for key, p in PLANS.items():
            lines.append(f"/buy {key}\n  {p['name']} - {p['desc']}\n")
        lines.append("\nExample: /buy monthly_basic")
        await _tg_send(chat_id, "\n".join(lines), telegram_api)


async def verify_and_credit(reference: str, engine) -> dict:
    if not reference:
        return {"error": "No reference"}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"},
        )
    data = r.json()

    if not data.get("status") or data["data"].get("status") != "success":
        return {"error": data.get("message", "Unverified")}

    tx = data["data"]
    meta = tx.get("metadata", {})
    telegram_id = int(meta.get("telegram_id", 0))
    plan_key = meta.get("plan", "per_view")
    plan = PLANS.get(plan_key, PLANS["per_view"])
    amount_ngn = tx["amount"] / 100
    paid_at = tx.get("paid_at", "")[:10]

    new_balance = 0
    if telegram_id:
        session = get_session(engine)
        try:
            add_credits(
                session, telegram_id,
                amount=plan["credits"],
                plan=plan_key,
                paystack_ref=reference,
                amount_ngn=amount_ngn,
            )
            new_balance = get_credit_balance(session, telegram_id)
        finally:
            session.close()

    return {
        "telegram_id": telegram_id,
        "plan": plan,
        "amount_ngn": amount_ngn,
        "paid_at": paid_at,
        "new_balance": new_balance,
        "reference": reference,
    }


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(PAYSTACK_SECRET.encode(), body, hashlib.sha512).hexdigest()
    return signature == expected


async def handle_paystack_webhook(body: bytes, signature: str, engine,
                                  telegram_api: str) -> dict:
    if not verify_webhook_signature(body, signature):
        return {"error": "Invalid signature"}

    event = json.loads(body)
    if event.get("event") != "charge.success":
        return {"ok": True}

    data = event.get("data", {})
    ref = data.get("reference", "")
    meta = data.get("metadata", {})
    telegram_id = int(meta.get("telegram_id", 0))
    plan_key = meta.get("plan", "per_view")

    if not telegram_id or not ref:
        return {"ok": True}

    plan = PLANS.get(plan_key, PLANS["per_view"])
    session = get_session(engine)
    try:
        add_credits(
            session, telegram_id,
            amount=plan["credits"],
            plan=plan_key,
            paystack_ref=ref,
            amount_ngn=plan["price_ngn"],
        )
    finally:
        session.close()

    await _tg_send(telegram_id,
        f"Payment confirmed!\n\n"
        f"Plan: {plan['name']}\n"
        f"Credits added: {plan['credits']}\n"
        f"Type /credits to see your balance.",
        telegram_api,
    )
    return {"ok": True}


RECEIPT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Payment Receipt — NGX Investment Bot</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #f0f4f8; display: flex;
           justify-content: center; align-items: center; min-height: 100vh; padding: 1rem; }}
    .card {{ background: #fff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.1);
             max-width: 440px; width: 100%; padding: 2rem; }}
    .badge {{ background: #dcfce7; color: #166534; border-radius: 50px; padding: .5rem 1.2rem;
              font-weight: 700; font-size: .9rem; display: inline-block; margin-bottom: 1.2rem; }}
    h1 {{ font-size: 1.5rem; color: #1e293b; margin-bottom: .25rem; }}
    .sub {{ color: #64748b; font-size: .9rem; margin-bottom: 1.5rem; }}
    .divider {{ border: none; border-top: 1px solid #e2e8f0; margin: 1.2rem 0; }}
    .row {{ display: flex; justify-content: space-between; padding: .45rem 0;
            font-size: .9rem; color: #334155; }}
    .row .label {{ color: #64748b; }}
    .row .value {{ font-weight: 600; }}
    .highlight {{ background: #f8fafc; border-radius: 10px; padding: .9rem 1rem; margin: 1rem 0; }}
    .credits {{ font-size: 2rem; font-weight: 800; color: #0ea5e9; text-align: center; }}
    .credits-label {{ text-align: center; color: #64748b; font-size: .85rem; margin-top: .2rem; }}
    .ref {{ font-size: .75rem; color: #94a3b8; word-break: break-all; margin-top: .5rem; }}
    .cta {{ display: block; text-align: center; margin-top: 1.5rem; background: #0ea5e9;
            color: #fff; text-decoration: none; border-radius: 10px; padding: .85rem;
            font-weight: 700; font-size: 1rem; }}
    .cta:hover {{ background: #0284c7; }}
    .footer {{ text-align: center; color: #94a3b8; font-size: .78rem; margin-top: 1rem; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">✓ Payment Successful</div>
    <h1>NGX Investment Bot</h1>
    <p class="sub">Official Payment Receipt</p>
    <div class="highlight">
      <div class="credits">{credits}</div>
      <div class="credits-label">Credits Added to Your Account</div>
    </div>
    <hr class="divider"/>
    <div class="row"><span class="label">Plan</span><span class="value">{plan_name}</span></div>
    <div class="row"><span class="label">Amount Paid</span><span class="value">₦{amount_ngn}</span></div>
    <div class="row"><span class="label">Date</span><span class="value">{paid_at}</span></div>
    <div class="row"><span class="label">Credits Before</span><span class="value">{credits_before}</span></div>
    <div class="row"><span class="label">Credits After</span><span class="value">{credits_after}</span></div>
    <div class="row"><span class="label">Status</span><span class="value" style="color:#16a34a">Confirmed</span></div>
    <p class="ref">Reference: {reference}</p>
    <hr class="divider"/>
    <a class="cta" href="https://t.me/Naija_Guru_Bot">Return to Telegram Bot →</a>
    <p class="footer">
      NGX Investment Intelligence · @Naija_Guru_Bot<br/>
      Keep this receipt for your records.
    </p>
  </div>
</body>
</html>"""
