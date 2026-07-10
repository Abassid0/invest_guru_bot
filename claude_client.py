import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_DIR = os.path.dirname(os.path.abspath(__file__))

OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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

NGX_SYSTEM_PROMPT = NGX_SYSTEM_PROMPT_TELEGRAM


def run_analysis(
    user_query: str,
    max_tokens: int = 1500,
    conversation_history: list | None = None,
    mode: str = "telegram",
) -> str:
    system = NGX_SYSTEM_PROMPT_TELEGRAM if mode == "telegram" else NGX_SYSTEM_PROMPT_API

    messages = [{"role": "system", "content": system}]
    if conversation_history:
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_query})

    with httpx.Client(timeout=90) as client:
        response = client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://investgurubot-production.up.railway.app",
                "X-Title": "NGX Investment Intelligence Bot",
            },
            json={
                "model": OPENROUTER_MODEL,
                "max_tokens": max_tokens,
                "messages": messages,
            },
        )

    if response.status_code != 200:
        error_detail = response.text[:200]
        raise Exception(f"OpenRouter API error {response.status_code}: {error_detail}")

    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise Exception("No response from model")

    result = (choices[0].get("message", {}).get("content") or "").strip()

    if mode == "telegram" and len(result) > 1400:
        result = result[:1380] + "\n\n(Type the command again with a ticker for more detail)"

    return result or "Sorry, I could not generate an analysis. Please try again."
