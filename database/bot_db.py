"""
Bot User Database — Credits, Subscriptions, Transactions, Referrals
All Telegram bot user data is stored here.
"""
import os
import random
import string
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Numeric, Text
from database.models import Base, get_session

FREE_CREDITS       = int(os.getenv("FREE_CREDITS_ON_SIGNUP", "3"))
REFERRAL_SIGNUP_BONUS   = 2   # extra credits for new user who uses a referral code
REFERRAL_PAYMENT_REWARD = 5   # credits given to referrer when their referral first pays


# ── Subscription plans (price in Kobo for Paystack — 1 NGN = 100 kobo) ───────
PLANS = {
    "per_view": {
        "name":     "Single Analysis",
        "price_kobo": 10_000,       # ₦100
        "price_ngn":  100,
        "credits":  1,
        "desc":     "1 analysis for ₦100",
    },
    "bundle_5": {
        "name":     "5-Pack Bundle",
        "price_kobo": 40_000,       # ₦400 (save ₦100)
        "price_ngn":  400,
        "credits":  5,
        "desc":     "5 analyses for ₦400 — save ₦100",
    },
    "bundle_10": {
        "name":     "10-Pack Bundle",
        "price_kobo": 70_000,       # ₦700 (save ₦300)
        "price_ngn":  700,
        "credits":  10,
        "desc":     "10 analyses for ₦700 — save ₦300",
    },
    "monthly_basic": {
        "name":     "Monthly Basic",
        "price_kobo": 200_000,      # ₦2,000
        "price_ngn":  2_000,
        "credits":  50,
        "desc":     "50 analyses/month for ₦2,000",
    },
    "monthly_premium": {
        "name":     "Monthly Premium",
        "price_kobo": 500_000,      # ₦5,000
        "price_ngn":  5_000,
        "credits":  200,
        "desc":     "200 analyses/month for ₦5,000",
    },
    "monthly_unlimited": {
        "name":     "Monthly Unlimited",
        "price_kobo": 1_000_000,    # ₦10,000
        "price_ngn":  10_000,
        "credits":  9999,
        "desc":     "Unlimited analyses for ₦10,000/month",
    },
}


# ── SQLAlchemy models ─────────────────────────────────────────────────────────

class BotUser(Base):
    """One row per Telegram user."""
    __tablename__ = "bot_users"

    telegram_id      = Column(BigInteger, primary_key=True)  # Telegram IDs exceed 32-bit int
    username         = Column(String(120))
    first_name       = Column(String(120))
    credits          = Column(Integer, default=FREE_CREDITS)
    referral_code    = Column(String(10), unique=True, nullable=False)
    referred_by_code = Column(String(10), nullable=True)   # code of who referred them
    total_referrals  = Column(Integer, default=0)          # how many people they referred
    paid_referrals   = Column(Integer, default=0)          # referrals who have paid
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)


class BotTransaction(Base):
    """Payment records."""
    __tablename__ = "bot_transactions"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id         = Column(BigInteger, nullable=False, index=True)  # BigInteger for Telegram IDs
    plan                = Column(String(50))
    amount_ngn          = Column(Numeric(12, 2))
    credits_added       = Column(Integer)
    paystack_reference  = Column(String(120), unique=True)
    status              = Column(String(20), default="pending")   # pending | success | failed
    referrer_rewarded   = Column(Boolean, default=False)
    created_at          = Column(DateTime, default=datetime.utcnow)


# ── Helper functions ──────────────────────────────────────────────────────────

def _gen_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def get_or_create_user(session, telegram_id: int, username: str = None,
                       first_name: str = None, referral_code_used: str = None) -> BotUser:
    user = session.query(BotUser).filter_by(telegram_id=telegram_id).first()
    if not user:
        bonus = FREE_CREDITS
        if referral_code_used:
            # Verify the referral code exists
            referrer = session.query(BotUser).filter_by(
                referral_code=referral_code_used.upper()
            ).first()
            if referrer and referrer.telegram_id != telegram_id:
                bonus += REFERRAL_SIGNUP_BONUS
                referrer.total_referrals += 1
                session.flush()

        user = BotUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            credits=bonus,
            referral_code=_gen_code(),
            referred_by_code=referral_code_used.upper() if referral_code_used else None,
        )
        session.add(user)
        session.commit()
    else:
        # Update name if changed
        if username:  user.username = username
        if first_name: user.first_name = first_name
        session.commit()
    return user


def get_credit_balance(session, telegram_id: int) -> int:
    user = session.query(BotUser).filter_by(telegram_id=telegram_id).first()
    return user.credits if user else 0


def deduct_credit(session, telegram_id: int) -> bool:
    """Deduct 1 credit. Returns True on success, False if insufficient credits."""
    user = session.query(BotUser).filter_by(telegram_id=telegram_id).first()
    if not user or user.credits <= 0:
        return False
    user.credits -= 1
    session.commit()
    return True


def add_credits(session, telegram_id: int, amount: int, plan: str = "",
                paystack_ref: str = None, amount_ngn: float = 0):
    """Add credits and record the transaction."""
    user = session.query(BotUser).filter_by(telegram_id=telegram_id).first()
    if not user:
        return
    user.credits += amount

    if paystack_ref:
        session.add(BotTransaction(
            telegram_id=telegram_id,
            plan=plan,
            amount_ngn=Decimal(str(amount_ngn)),
            credits_added=amount,
            paystack_reference=paystack_ref,
            status="success",
        ))

    session.commit()

    # Reward referrer on first payment
    if paystack_ref and user.referred_by_code:
        _reward_referrer(session, user.referred_by_code, telegram_id, paystack_ref)


def _reward_referrer(session, referral_code: str, new_payer_id: int, paystack_ref: str):
    """Give credits to the referrer when someone they referred makes their first payment."""
    # Only reward once per referred user
    already = session.query(BotTransaction).filter(
        BotTransaction.telegram_id == new_payer_id,
        BotTransaction.status == "success",
        BotTransaction.referrer_rewarded == True,
    ).first()
    if already:
        return

    referrer = session.query(BotUser).filter_by(referral_code=referral_code).first()
    if not referrer:
        return

    referrer.credits += REFERRAL_PAYMENT_REWARD
    referrer.paid_referrals += 1

    # Mark this transaction so we don't double-reward
    txn = session.query(BotTransaction).filter_by(paystack_reference=paystack_ref).first()
    if txn:
        txn.referrer_rewarded = True

    session.commit()


def get_user_stats(session, telegram_id: int) -> dict:
    user = session.query(BotUser).filter_by(telegram_id=telegram_id).first()
    if not user:
        return {}
    txns = session.query(BotTransaction).filter_by(
        telegram_id=telegram_id, status="success"
    ).all()
    total_spent = sum(float(t.amount_ngn or 0) for t in txns)
    return {
        "credits":        user.credits,
        "referral_code":  user.referral_code,
        "total_referrals": user.total_referrals,
        "paid_referrals": user.paid_referrals,
        "total_spent_ngn": total_spent,
        "member_since":   user.created_at.strftime("%b %Y") if user.created_at else "N/A",
    }
