"""
Referral System — wraps bot_db referral logic for Telegram display.
"""
from database.bot_db import get_user_stats


def referral_message(session, telegram_id: int, bot_username: str = "Naija_Guru_Bot") -> str:
    stats = get_user_stats(session, telegram_id)
    ref_code = stats.get("referral_code", "N/A")
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"

    return (
        f"Your Referral Programme\n\n"
        f"Your code: {ref_code}\n"
        f"Your link: {ref_link}\n\n"
        f"How it works:\n"
        f"- Share your link with friends\n"
        f"- They join and get 2 BONUS credits\n"
        f"- When they make their FIRST payment, you get 5 FREE credits\n\n"
        f"Your referrals: {stats.get('total_referrals', 0)} joined, "
        f"{stats.get('paid_referrals', 0)} paid\n\n"
        f"Share now and earn!"
    )
