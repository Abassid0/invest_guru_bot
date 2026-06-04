# NGX Investment Intelligence Bot — User Guide
### @Naija_Guru_Bot on Telegram

---

## What Is This Bot?

Think of this bot as your personal Nigerian investment analyst — available 24/7 on Telegram. It gives you the same quality of analysis that wealthy Nigerians pay stockbrokers thousands of naira for, completely on demand.

You can ask it about:
- Any stock listed on the Nigerian Exchange (NGX)
- Treasury bills and government bonds
- CBN interest rates and inflation
- Whether to put your money in stocks or T-bills
- How risky a stock is before you buy

**No financial jargon needed.** Ask questions the same way you would ask a knowledgeable friend.

---

## Getting Started (3 Steps)

### Step 1 — Find the Bot
1. Open Telegram on your phone or computer
2. Tap the search icon (🔍) at the top
3. Type **@Naija_Guru_Bot**
4. Tap on the bot when it appears

### Step 2 — Start the Conversation
1. Tap the **START** button (or type `/start` and press send)
2. The bot will greet you and show you all available commands

### Step 3 — Ask Your Question
Type any command or just ask your question in plain English. Examples:
- `/analyse GTCO`
- `Should I buy Dangote Cement shares?`
- `/macro`

That's it. No registration, no password, no complicated setup.

---

## Scenario-Based Guide

Each scenario below is a real situation Nigerians face when investing. Find the one that matches your question.

---

### Scenario 1: "I Have ₦200,000 — Should I Put It in Stocks or T-Bills?"

**You're thinking:** *I have some savings. I don't want to just leave it in a savings account earning 4%. Should I invest in stocks or the government's treasury bills?*

**What to type:**
```
/compare
```

**What you'll get:**
A clear comparison showing:
- Current 91-day T-bill rate (e.g., 23.7% per year)
- Average NGX stock market returns
- Which gives better returns right now
- The risk level of each option

**Follow-up you can ask:**
```
I have N200,000 and I am not a risk taker. Which is better for me right now?
```

---

### Scenario 2: "I've Heard About GTCO — Is It a Good Buy?"

**You're thinking:** *My colleague at work mentioned Guaranty Trust (GTCO). He says it's a solid bank stock. But is now the right time to buy?*

**What to type:**
```
/analyse GTCO
```

**What you'll get:**
- Current share price
- Whether the stock is overpriced, fairly priced, or cheap right now
- How the stock has been performing recently
- A recommendation (BUY / HOLD / SELL / AVOID)

**Want more depth? Try these:**
```
/value GTCO
```
→ Shows you exactly what the stock is worth (fair price) and whether current price is a bargain

```
/technical GTCO
```
→ Tells you: if you're buying today, at what price should you place your order, where to put your stop-loss, and what profit target to aim for

---

### Scenario 3: "I Already Own Dangote Cement Shares — Should I Keep Them?"

**You're thinking:** *I bought DANGCEM shares 6 months ago. The price has been going up and down. Should I hold on or sell?*

**What to type:**
```
/debate DANGCEM
```

**What you'll get:**
A balanced bull vs bear analysis:
- **Bull case** (reasons the stock will go up)
- **Bear case** (reasons the stock might fall)
- A final verdict on whether the bulls or bears are stronger right now

**Also useful:**
```
/risk DANGCEM
```
→ Shows you exactly how risky this stock is. Includes: worst-case scenarios, how much you could lose, and at what price you should sell to protect yourself.

---

### Scenario 4: "I Want to Know What's Happening With the Economy"

**You're thinking:** *The dollar rate is confusing me. Inflation is high. What does the CBN's interest rate mean for my investments?*

**What to type:**
```
/macro
```

**What you'll get instantly (from live data):**
- CBN Monetary Policy Rate (MPR) — the master interest rate
- Current inflation rate (headline CPI)
- Official USD/NGN exchange rate
- Parallel market rate
- 91-day T-bill rate
- Current oil price (Brent crude)

**Want deeper analysis? Ask:**
```
How does the current CBN interest rate affect bank stocks?
```
or
```
Is inflation going up or down and what should I do with my investments?
```

---

### Scenario 5: "I Want to Put Money in Treasury Bills"

**You're thinking:** *I heard the government is paying about 23% on T-bills. That sounds better than my bank's savings account. How do I understand this properly?*

**What to type:**
```
/tbills
```

**What you'll get:**
- Current NTB (Nigerian Treasury Bill) auction rates
- 91-day, 182-day, and 364-day rates compared
- How T-bills work in simple language
- Whether rates are going up or down

**Follow-up question:**
```
If I invest N500,000 in 91-day T-bills, how much will I earn?
```

---

### Scenario 6: "I Want to Spread My Money Across Multiple Stocks"

**You're thinking:** *I have ₦1 million to invest. I don't want to put all my eggs in one basket. Which combination of stocks gives me the best balance of safety and returns?*

**What to type:**
```
/portfolio GTCO DANGCEM MTNN SEPLAT
```
(Replace with the stocks you're considering)

**What you'll get:**
- How well these stocks complement each other
- Which sectors you're exposed to
- Whether your mix is too risky or well-balanced
- Suggestions to improve your portfolio

---

### Scenario 7: "I Want to Compare Two Stocks"

**You're thinking:** *Should I buy Zenith Bank or GTBank? They're both big banks but which one is the better investment right now?*

**Just type it naturally:**
```
Compare ZENITHBANK and GTCO — which is the better investment right now?
```

The bot understands plain English. You don't need a special command for this.

---

### Scenario 8: "Something Is Happening in the News — How Does It Affect My Investments?"

**You're thinking:** *I just saw that the US raised interest rates, or that oil prices are falling, or that there's political news. What does this mean for my NGX stocks?*

**What to type:**
```
/global oil price falling to $60
```
or
```
/global US interest rate hike
```
or just ask:
```
How does a drop in oil prices affect Nigerian bank stocks?
```

---

### Scenario 9: "I Want Regular Dividend Income"

**You're thinking:** *I'm not interested in buying and selling stocks. I just want stocks that pay me regular dividends, like a rental income from my money.*

**What to type:**
```
/dividend
```

**What you'll get:**
- Best dividend-paying stocks on NGX
- Which mutual funds pay the most returns
- Dividend yield percentages compared
- Which pays quarterly vs annually

---

### Scenario 10: "I Want to Test If a Strategy Would Have Made Money in the Past"

**You're thinking:** *Before I invest real money, I want to see how a strategy would have performed historically. If I had bought inflation-beating stocks every quarter for 3 years, how much would I have made?*

This is called **backtesting** — running your strategy against historical data to see how it would have performed.

**Test the inflation-beating strategy (default — last 3 years):**
```
/backtest
```

**What you'll get:**
```
Backtest: Inflation Beater Strategy
Period: Jun 2023 — Jun 2026 (3 years)

Total Return:     +58.3%
Annual Return:    +16.8%
Sharpe Ratio:     1.52  (good risk-adjusted return)
Max Drawdown:     -22.1% (worst loss from peak)
Win Rate:         65%   (most trades profitable)
Final Value:      N1,583,000 (started with N1,000,000)
Total Trades:     120
```

**Test with custom settings:**
```
/backtest 5years
```
→ Tests the last 5 years instead of 3

```
/backtest 2021-01-01 2024-01-01
```
→ Tests a specific date range (bull market, bear market, etc.)

**Test holding specific stocks (buy-and-hold):**
```
/backtest hold GTCO DANGCEM ZENITHBANK
```
→ Shows how ₦1,000,000 split equally across these 3 stocks would have performed

**Compare both strategies:**
```
/backtest compare
```
→ Shows inflation-beater strategy vs buy-and-hold side by side

**Understanding your results:**

| Metric | What it means | Good value |
|--------|--------------|-----------|
| Total Return | Overall profit/loss % | Above 30% for 3 years |
| Annual Return | Yearly average return | Above 15% (beats inflation) |
| Sharpe Ratio | Return vs risk taken | Above 1.0 |
| Max Drawdown | Worst loss you'd experience | Better than -30% |
| Win Rate | % of trades that were profitable | Above 55% |

**Real scenario example:**
> "Before I invest my ₦2 million in NGX stocks, I want to see how the inflation-beating strategy would have done over the last 5 years."

```
/backtest 5years
```
The bot fetches historical data, simulates quarterly rebalancing, and shows you exactly how ₦1,000,000 would have grown.

---

### Scenario 11: "I Want to Know If a Stock Is Financially Healthy"

**You're thinking:** *Before I invest my money, I want to make sure the company is not hiding problems in its accounts. Is this company really profitable?*

**What to type:**
```
/financials FBNH
```

**What you'll get:**
- 5-year revenue and profit trend
- Whether earnings are growing or shrinking
- Red flags in the financial statements
- Key ratios explained in simple language (ROE, debt levels, etc.)

---

## Quick Command Reference Card

Copy this and save it on your phone:

```
STOCK ANALYSIS
/analyse TICKER     — Is this stock good to buy?
/technical TICKER   — Entry price, stop-loss, and target
/value TICKER       — What is this stock really worth?
/risk TICKER        — How risky is this stock?
/financials TICKER  — Is the company financially healthy?
/moat TICKER        — Does this company have an edge?
/growth TICKER      — What is the growth outlook?
/institutional TICKER — What do big investors think?
/debate TICKER      — Buy side vs sell side verdict
/earnings TICKER    — Latest earnings performance
/sentiment TICKER   — Market mood on this stock

FIXED INCOME
/tbills             — Treasury bill rates today
/bonds              — Government bond rates
/funds              — Best mutual funds right now
/compare            — Stocks vs T-bills right now

MACRO & ECONOMY
/macro              — CBN rate, inflation, FX rates
/dividend           — Best stocks for dividend income
/global EVENT       — How news affects NGX
/portfolio TICKERS  — Is my portfolio balanced?

BACKTESTING (Test strategies on historical data)
/backtest           — Test inflation-beating strategy (last 3 years)
/backtest 5years    — Test the last 5 years
/backtest YYYY-MM-DD YYYY-MM-DD  — Test a custom date range
/backtest hold TICKER1 TICKER2   — Test buy-and-hold specific stocks
/backtest compare   — Compare inflation strategy vs buy-and-hold
```

**Replace TICKER** with the stock code. Examples:
- Banking: GTCO, ZENITHBANK, ACCESSCORP, UBA, FBNH
- Cement: DANGCEM, BUACEMENT
- Telecoms: MTNN, AIRTELAFRI
- Oil: SEPLAT, TOTAL
- FMCG: NESTLE, FLOURMILL

---

## Tips for Getting the Best Answers

**Tip 1 — Be specific about your situation**

Instead of:
> "Should I buy stocks?"

Say:
> "I have N500,000, I am 35 years old, I need the money in 2 years. Should I buy GTCO shares or put the money in T-bills?"

**Tip 2 — Ask follow-up questions**

After any analysis, you can ask:
> "What price should I buy at?"
> "What are the biggest risks?"
> "How does this compare to Zenith Bank?"

**Tip 3 — Ask in plain English**

You don't always need commands. These all work:
- "Is MTN Nigeria a good long-term investment?"
- "My DANGCEM shares are down 15%. Should I sell or hold?"
- "What happens to bank stocks when CBN raises interest rates?"

**Tip 4 — Specify your risk tolerance**

Always mention if you're cautious or aggressive:
- "I am a conservative investor..."
- "I can afford to lose this money if needed..."

---

## Important Disclaimer

> ⚠️ **This bot provides educational information and analysis only.**
> It is NOT a licensed stockbroker or financial adviser.
> Always verify information and consider consulting a SEC-registered investment adviser before making investment decisions.
> Past performance of any stock does not guarantee future results.
> Investing involves risk, including possible loss of capital.

---

## Frequently Asked Questions

**Q: Is this bot free to use?**
A: Yes, completely free.

**Q: How current is the data?**
A: The bot searches the internet in real-time when you ask about a specific stock or market event. Macro data (CBN rates, FX, Brent crude) updates daily.

**Q: Can it analyse any Nigerian stock?**
A: Yes. It can analyse any of the 155+ companies listed on the Nigerian Exchange (NGX), not just the ones in the database.

**Q: Can I trust the analysis?**
A: The bot uses the same analytical frameworks as professional investment analysts. However, no analysis is 100% accurate — markets are unpredictable. Always do your own research.

**Q: What if the bot gives a wrong answer?**
A: Ask a follow-up question to clarify, or rephrase your question. If an analysis seems off, cross-check with your stockbroker.

**Q: Does the bot store my personal information?**
A: No. The bot only processes your messages to generate responses. No personal financial data is stored.

---

*NGX Investment Intelligence Bot — Powered by AI*
*@Naija_Guru_Bot on Telegram*
