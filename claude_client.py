import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None
_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_skill(filename: str, fallback: str) -> str:
    path = os.path.join(_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return fallback
    return raw.split("---", 2)[-1].strip() if "---" in raw else raw


_SKILL_FULL = _load_skill("SKILL.md", "You are an expert Nigerian capital markets analyst.")
_SKILL_LITE = _load_skill("SKILL_LITE.md", "You are a plain-English Nigerian investment adviser.")

NGX_SYSTEM_PROMPT_API = f"""
You are an institutional-grade Nigerian capital markets analyst.
{_SKILL_FULL}
""".strip()

NGX_SYSTEM_PROMPT_TELEGRAM = _SKILL_LITE

# Backwards compat
NGX_SYSTEM_PROMPT = NGX_SYSTEM_PROMPT_TELEGRAM


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def run_analysis(
    user_query: str,
    max_tokens: int = 1500,
    conversation_history: list | None = None,
    mode: str = "telegram",
) -> str:
    client = get_client()

    system = NGX_SYSTEM_PROMPT_TELEGRAM if mode == "telegram" else NGX_SYSTEM_PROMPT_API

    messages = []
    if conversation_history:
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_query})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=messages,
    )

    text_parts = [
        block.text
        for block in response.content
        if hasattr(block, "text") and block.text
    ]
    result = "\n".join(text_parts).strip()

    if mode == "telegram" and len(result) > 1400:
        result = result[:1380] + "\n\n(Type the command again with a ticker for more detail)"

    return result or "Sorry, I could not generate an analysis. Please try again."
