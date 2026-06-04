import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None

# Load master skill as system prompt (same directory as this file)
_SKILL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")
try:
    with open(_SKILL_PATH, "r", encoding="utf-8") as _f:
        _RAW_SKILL = _f.read()
except FileNotFoundError:
    _RAW_SKILL = "You are an expert Nigerian capital markets analyst."

# Strip YAML front-matter, keep body
_SKILL_BODY = _RAW_SKILL.split("---", 2)[-1].strip() if "---" in _RAW_SKILL else _RAW_SKILL

NGX_SYSTEM_PROMPT = f"""
You are an institutional-grade Nigerian capital markets analyst and investment strategist
delivering analysis via a Telegram bot for retail and professional Nigerian investors.

{_SKILL_BODY}

TELEGRAM FORMATTING RULES (strict):
- Use *bold* for section headers and key figures
- Use `code` for ticker symbols, rates, and prices
- Use plain dashes for bullet points
- Tables use plain pipe format (Telegram renders them as code blocks)
- Never use ### headers — use *bold* instead
- Keep every response under 3,800 characters (Telegram hard limit is 4,096)
- If content exceeds limit, summarise and offer deeper follow-up commands
""".strip()


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def run_analysis(user_query: str, max_tokens: int = 1500) -> str:
    client = get_client()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=NGX_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_query}],
    )

    text_parts = [
        block.text
        for block in response.content
        if hasattr(block, "text") and block.text
    ]
    result = "\n".join(text_parts).strip()

    if len(result) > 3800:
        result = result[:3750] + "\n\n_...truncated. Use a more specific command for focused output._"

    return result or "Sorry, I could not generate an analysis. Please try again."
