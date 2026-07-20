# Investment Guru Bot

AI-powered Nigerian stock market intelligence, delivered through Telegram.

**[@Naija_Guru_Bot](https://t.me/Naija_Guru_Bot)** gives everyday Nigerians the same caliber of market analysis that institutional investors pay for — in plain English, on demand, for a fraction of the cost.

---

## What It Does

- **146+ NGX stocks** tracked in real time across 11 sectors
- **AI-driven analysis** powered by Claude (via OpenRouter) — ask about any stock in plain English
- **Inflation benchmarking** — every recommendation measured against Nigeria's CPI so you know if a stock actually grows your wealth
- **Backtesting engine** — test strategies against historical data before risking capital
- **Currency devaluation strategy** — identifies stocks with FX revenue exposure that hedge against naira depreciation
- **Watchlist & price alerts** — set target prices and get notified when they hit
- **Macro dashboard** — CBN MPR, T-bill rates, inflation, USD/NGN, Brent crude in one view
- **Conversation memory** — the bot remembers context within a session for follow-up questions

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Railway (Production)                  │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ FastAPI   │◄──│ Telegram     │    │ Data Sync     │  │
│  │ REST API  │   │ Webhook      │    │ (Daily Cron)  │  │
│  └────┬─────┘    └──────┬───────┘    └───────┬───────┘  │
│       │                 │                    │          │
│       │          ┌──────▼───────┐            │          │
│       │          │ bot/handlers │            │          │
│       │          │ bot/paystack │            │          │
│       │          │ bot/alerts   │            │          │
│       │          └──────┬───────┘            │          │
│       │                 │                    │          │
│       │          ┌──────▼───────┐     ┌──────▼───────┐  │
│       │          │ Claude AI    │     │ NGX Pulse    │  │
│       │          │ (OpenRouter) │     │ NGX Group    │  │
│       │          └──────────────┘     │ Yahoo Finance│  │
│       │                               │ CBN API      │  │
│       ▼                               └──────┬───────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Supabase PostgreSQL                 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Data Sources

| Data           | Primary Source                      | Fallback                        |
|----------------|-------------------------------------|---------------------------------|
| Stock prices   | NGX Pulse API (ngxpulse.ng)         | NGX Group REST → Yahoo Finance  |
| FX rates       | ExchangeRate-API                    | —                               |
| Brent crude    | Yahoo Finance (BZ=F)                | —                               |
| MPR & T-bills  | CBN JSON API                        | —                               |
| Inflation      | CBN JSON API                        | NBS scraper                     |

## Telegram Commands

### Free Commands
| Command          | Description                                      |
|------------------|--------------------------------------------------|
| `/start`         | Welcome message and command overview              |
| `/help`          | Full command list with examples                   |
| `/credits`       | Check your remaining analysis credits             |
| `/macro`         | Live macro snapshot (MPR, T-bills, inflation, FX) |
| `/watch TICKER`  | Set a price alert for a stock                     |
| `/watchlist`     | View your active price watches                    |
| `/unwatch TICKER`| Remove a price alert                              |
| `/rate N`        | Rate your last analysis (1-5)                     |
| `/refer`         | Get your referral link for free credits           |
| `/buy`           | Purchase more analysis credits via Paystack       |

### Paid Analysis (1 credit each)
| Command               | Description                                          |
|-----------------------|------------------------------------------------------|
| `/analyse TICKER`     | Full stock analysis with BUY/HOLD/AVOID verdict       |
| `/compare`            | Stocks vs T-bills — where should your money go?       |
| `/sector SECTOR`      | Sector breakdown with top picks                       |
| `/risk TICKER`        | Volatility, drawdown, and risk-adjusted returns       |
| `/dividend TICKER`    | Dividend yield and payout history                     |
| `/portfolio`          | Portfolio construction advice                         |
| `/devaluation`        | FX hedge strategy — stocks that protect against naira fall |
| `/backtest`           | Test an investment strategy against historical data   |

You can also ask questions in plain English — no commands needed:
> "Should I buy Dangote Cement shares?"
> "I have N500k — stocks or T-bills?"

## Project Structure

```
investment-guru/
├── main.py                  # FastAPI entrypoint — REST API + webhook routing
├── bot/
│   ├── handlers.py          # All Telegram command logic
│   ├── paystack.py          # Payment processing (Paystack)
│   ├── alerts.py            # Watchlist price alert checks
│   └── referral.py          # Referral system logic
├── database/
│   ├── models.py            # SQLAlchemy models (Company, StockPrice, etc.)
│   └── bot_db.py            # User, credit, conversation, watchlist CRUD
├── scrapers/
│   ├── price_scraper.py     # NGX Group REST API scraper
│   ├── ngx_production_scraper.py  # Multi-source price fetcher
│   ├── nbs_inflation_scraper.py   # NBS inflation data
│   └── financial_scraper.py       # Company financial statements
├── calculators/
│   └── inflation_calculator.py    # Inflation-adjusted return calculations
├── claude_client.py         # AI analysis via OpenRouter/Claude
├── data_sync.py             # Daily data pipeline (prices, FX, macro)
├── backtesting_engine.py    # Historical strategy backtesting
├── backtest_api_routes.py   # Backtest REST endpoints
├── scheduler.py             # Cron job runner
├── scripts/
│   ├── add_all_stocks.py    # Seed 146+ stocks across 11 sectors
│   └── migrate_schema.py    # Database migration utility
├── static/
│   └── dashboard.html       # Admin analytics dashboard
├── SKILL.md                 # System prompt (API/dashboard mode)
├── SKILL_LITE.md            # System prompt (Telegram — plain English)
└── USER_GUIDE.md            # End-user guide for Telegram bot
```

## REST API

The FastAPI server exposes these endpoints:

| Endpoint                        | Method | Description                        |
|---------------------------------|--------|------------------------------------|
| `/api/stocks`                   | GET    | All active stocks with latest price|
| `/api/stocks/{ticker}`          | GET    | Detailed stock data + performance  |
| `/api/sectors`                  | GET    | Sector breakdown                   |
| `/api/inflation-beaters`        | GET    | Stocks beating inflation           |
| `/api/macro`                    | GET    | Current macro indicators           |
| `/api/search?q=`               | GET    | Search stocks by name or ticker    |
| `/api/sync`                     | POST   | Trigger data sync (admin)          |
| `/api/backtest/*`               | POST   | Run backtesting strategies         |
| `/health`                       | GET    | Health check                       |
| `/health/db`                    | GET    | Database connectivity check        |

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (Supabase recommended)
- Telegram Bot Token (via [@BotFather](https://t.me/BotFather))
- Paystack account (for payments)
- OpenRouter API key (for Claude AI)

### Installation

```bash
git clone https://github.com/Abassid0/invest_guru_bot.git
cd invest_guru_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:

| Variable              | Description                          |
|-----------------------|--------------------------------------|
| `DATABASE_URL`        | PostgreSQL connection string         |
| `TELEGRAM_BOT_TOKEN`  | From @BotFather                     |
| `WEBHOOK_URL`         | Your deployed app URL               |
| `OPENROUTER_API_KEY`  | OpenRouter API key for Claude       |
| `PAYSTACK_SECRET_KEY` | Paystack secret key                 |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key                 |
| `NGX_PULSE_API_KEY`   | NGX Pulse API key (stock data)      |
| `SUPABASE_URL`        | Supabase project URL                |
| `SUPABASE_SERVICE_KEY`| Supabase service role key           |

### Database Setup

```bash
python scripts/migrate_schema.py   # Create tables
python scripts/add_all_stocks.py   # Seed 146+ stocks
python data_sync.py                # Initial data fetch
```

### Run Locally

```bash
uvicorn main:app --reload --port 8000
```

### Deploy to Railway

The project includes `railway.toml` with:
- Automatic builds via Railpack
- Health check on `/health`
- Daily data sync cron at 4 PM UTC (market close)

```bash
railway up
```

## Monetization

Credit-based micropayment model via Paystack:

| Plan       | Credits | Price      |
|------------|---------|------------|
| Starter    | 10      | ₦1,500    |
| Pro        | 30      | ₦3,500    |
| Premium    | 100     | ₦9,500    |

New users receive 3 free credits on signup. Referrals earn 2 bonus credits.

## Tech Stack

- **Runtime**: Python 3.11, FastAPI, Uvicorn
- **AI**: Claude (Anthropic) via OpenRouter
- **Database**: PostgreSQL on Supabase
- **Payments**: Paystack
- **Deployment**: Railway (with cron scheduling)
- **Data**: NGX Pulse API, CBN API, Yahoo Finance, ExchangeRate-API

## License

Proprietary. All rights reserved.
