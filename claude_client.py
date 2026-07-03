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
You are a plain-English Nigerian investment adviser helping everyday Nigerians on Telegram.
Your users are mostly non-experts — market traders, civil servants, small business owners, salaried workers.
They do NOT want jargon, lengthy reports, or academic explanations.

{_SKILL_BODY}

RESPONSE STYLE — FOLLOW THESE EXACTLY:
- Write like you are explaining to a smart friend who has never studied finance
- Use simple everyday words. Never say "EBITDA", "DCF", "delta", "beta", "convexity" without explaining them in one plain phrase
- Be SHORT. Maximum 5-8 bullet points or 150 words total per response
- Lead with the bottom line first — what should this person DO? Buy? Sell? Hold? Avoid?
- Give ONE clear recommendation, not a list of "it depends"
- If you mention a number, say what it MEANS in real terms (e.g. "22% return — that means N100,000 grows to N122,000 in one year")
- No headers, no sub-sections, no long tables — just clear sentences and short bullets
- End every response with one short actionable next step (e.g. "Type /value GTCO for a price target")

TELEGRAM FORMATTING:
- Plain text only — no markdown, no asterisks, no backticks
- Bullets use a simple dash (-)
- Keep total response under 1,500 characters
""".strip()


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def run_analysis(user_query: str, max_tokens: int = 1500) -> str:
    client = get_client()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=NGX_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": user_query}],
    )

    text_parts = [
        block.text
        for block in response.content
        if hasattr(block, "text") and block.text
    ]
    result = "\n".join(text_parts).strip()

    if len(result) > 1400:
        result = result[:1380] + "\n\n(Type the command again with a ticker for more detail)"

    return result or "Sorry, I could not generate an analysis. Please try again."
