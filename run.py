"""
Unified launcher for the NGX Investment Intelligence platform.

Usage:
    python run.py          # Start the FastAPI server (default)
    python run.py api      # Start the FastAPI server
    python run.py bot      # Start the Telegram bot (polling mode)
"""
import subprocess
import sys
import os


def run_api():
    port = os.getenv("PORT", "8000")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", port, "--reload",
    ])


def run_bot():
    from bot.production_bot import main as bot_main
    bot_main()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "api":
        run_api()
    elif mode == "bot":
        run_bot()
    else:
        print(f"Unknown mode: {mode}. Use 'api' or 'bot'.")
        sys.exit(1)
