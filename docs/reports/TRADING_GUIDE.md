# How to Trade BTC Trend Rider v5.2 / v6 — Complete Guideline

> **v6 update (2026-07):** a **short sleeve for bear markets** was added on top
> of the unchanged v5.2 long engine — see **§10**. Use `BTC_Trend_Rider_v6.pine`.
> With it, the backtested bear year turns from −2% into **+31.7%**
> (full research: `LONGSHORT_REPORT.md`). Sections 1–9 (the long side) are
> unchanged and still apply exactly as written.
>
> **v5.2 update (2026-07):** TP1 now sells **40%** of the position instead of 50%
> (keeps more of the runner — validated in and out of sample, see
> `IMPROVEMENT_REPORT.md`). Everywhere this guide says "half", use 40%.
> Recommended risk: **3–5% of account per trade** (see §6 and §8).

Every example below is a **real trade from the 3-year backtest** (real Binance prices, fees included). Nothing is invented.

---

## 1. One-time setup (5 minutes)

1. Open TradingView → chart **BTCUSDT** (Binance) → set timeframe to **4h**.
2. Open Pine Editor → paste `BTC_Trend_Rider_v5.pine` → "Add to chart".
3. You will see:
   - **Red thick line** = SMA200, **orange** = EMA50, **maroon** = EMA200 (the trend filter)
   - **Blue line** = EMA20 (the pullback line)
   - **Green background** = regime ON (trading allowed). **Red background** = regime OFF (no trading).
   - **Status table** (top-right) tells you the current state: REGIME ON/OFF, FLAT / OPEN / RUNNER / HALTED.
4. Create alert: Alert → Condition = "BTC Trend Rider v5.1" → **"Order fills and alert() function calls"** → set to "Open-ended". Now your phone gets every BUY, TP1, and EXIT — you don't need to watch the chart.

**Golden rule: the candle must CLOSE first.** All decisions happen when a 4h candle closes (every 4 hours). Never act in the middle of a candle.

---

## 2. WHEN TO BUY

Buy **only** when BOTH conditions are true:

**Condition A — the regime is ON (green background):**
- Price is above the SMA200 (red line), AND
- EMA50 (orange) is above EMA200 (maroon)

**Condition B — one of these two entry triggers:**

| Trigger | What it looks like |
|---|---|
| **1. Fresh trend** | Background just turned from red to green → buy at the open of the next candle |
| **2. Pullback resume** | Background is green, price dipped **below the blue EMA20**, and now a candle **closes back above** it → buy at the open of the next candle |

The script prints a green **BUY** triangle and sends an alert — you don't have to spot this yourself.

**At the moment you buy, write down 3 numbers** (the script draws them as lines):
- **Entry** = your buy price (blue line)
- **Stop loss** = entry − 2.5 × ATR (red line) → put a real stop-loss order here immediately
- **TP1** = entry + the same distance (green line) → put a sell order for **40%** of your position here

> **Real example — the buy:** 2024-11-05 08:00 UTC. Regime green, price had dipped below EMA20 and closed back above.
> Buy at **$68,894** · Stop at **$66,586** · TP1 at **$71,202**.

---

## 3. WHAT TO DO AFTER YOU BUY (managing the trade)

This is your own method, now with tested numbers:

**Step 1 — Wait for TP1 (sell 40%).**
When price reaches TP1, your sell order fills → **40% of the position is sold at +1R profit** (v5.2: keep 60% as the runner — the backtest shows selling more here costs real money).

**Step 2 — Immediately move your stop loss up to your entry price.**
From this moment the trade **cannot lose money**. Worst case you exit at entry, keeping the TP1 profit. (This is your "put stoploss to the entered line" rule — it's what makes the system safe.)

**Step 3 — Trail the runner (the remaining 60%).**
After every 4h candle closes, calculate: `highest high since entry − 4 × ATR(14)`.
If that number is **higher** than your current stop → move the stop up to it. **Never move a stop down.** The chart's red line shows the correct stop at all times, and the status table shows "RUNNER (BE locked)".

**Step 4 — Do nothing else.** No panic-selling, no adding, no "taking profit early because it feels high." The runner is where the big money comes from.

> **Real example — the full winner:** the trade above bought at $68,894.
> TP1 hit at **$71,202** → sold half (+3.3%), stop moved to $68,894 (breakeven).
> Then BTC ran for 20 days while the trailing stop followed it up. The runner was finally stopped out on 2024-11-25 at **$94,972**.
> **Total trade: +20.5% on the whole account.** This one trade is why you hold runners.

---

## 4. WHEN TO SELL (all exit rules)

You sell when **any one** of these happens — never for any other reason:

| # | Exit rule | What you do |
|---|---|---|
| 1 | **Price hits your stop loss** (before TP1) | Full exit. This is a normal small loss, ~2-6%. Accept it. |
| 2 | **Runner hits the trailing stop** (after TP1) | Exit the rest. This is how winners end — often far above entry. |
| 3 | **Regime turns OFF** (background turns red: price closes under SMA200 or EMA50 crosses under EMA200) | Sell **everything at the next open**, even at a loss. This rule is what saved −45% in the 2025-26 bear market. |
| 4 | **Monthly circuit-breaker**: your account is down **4% within one calendar month** | Sell everything and **do not trade again until the 1st of the next month.** The table shows "HALTED". |

> **Real example — a normal stop-out (rule 1):** 2025-01-20, bought a pullback at **$107,121**, stop at $101,081. Eight hours later the stop was hit: **−5.7%**. Nothing was wrong — this is a planned, small, survivable loss. The next trades made it back.
>
> **Real example — a breakeven scratch (rule 2):** 2023-07-09, bought at **$30,349**, TP1 hit at $30,979 (half sold, +2%), stop moved to entry. Market turned, runner stopped at $30,349. **Trade result: +0.96%.** A trade that "failed" still made money — that's your breakeven rule working.
>
> **Real example — regime death (rule 3):** 2023-07-20, bought a fresh regime at **$29,948**; twelve hours later the regime flipped off. Sold at $29,810: **−0.5%** and flat. Boring — and exactly right: never argue with a dead trend.

---

## 5. WHEN TO HOLD / DO NOTHING

Doing nothing is a position in this system. You are **flat and waiting** whenever:

- **Background is red (regime OFF)** — no buys, ever, no matter how cheap BTC looks. In the backtest the system sat flat through most of the 2025-26 crash and lost only −1.7% while holders lost −45%. Sitting out IS the edge.
- **Regime is green but there's no signal** — price is just running above EMA20 with no fresh pullback-resume. Wait for the script's triangle.
- **You are HALTED (monthly breaker)** — down 4% this month → no trades until next month, even if signals appear. The backtest proves skipping those signals *increases* profit.
- **You are in a trade and no exit rule has fired** — hold. Don't touch the position between 4h closes.

Whole months can be flat (7 of the 36 backtested months had zero or no trades). That is normal and correct.

---

## 6. Risk rules (do not skip)

- The backtest assumes each trade uses your full trading balance with a 2.5×ATR stop → a typical loss is **2-6% of the account**. If that feels heavy, set "Order size" in the strategy Properties to **50%** — the backtest shows worst month shrinks to −3.9% and drawdown to −8.4%.
- **Never move a stop down. Never skip the stop. Never revenge-trade after a loss.** The circuit-breaker exists because the data shows post-loss chop keeps losing.
- Expect, honestly: about **2 profitable months for every losing month**, worst month around −5%, best months +10-20%, and flat stretches in bear markets. About half of all trades will be small losses or scratches — the yearly profit comes from a handful of big runners (+8% to +20% each). If you close runners early, you delete the whole edge.
- This is 4h trading: you check the chart **once every 4 hours at most**, or just act on alerts. More screen time = more mistakes.

---

## 7. Your routine (summary card)

**Every 4h candle close (or on alert):**
1. Flat? → Is background green AND did a BUY triangle appear? → Buy at next open, set stop + TP1 order.
2. In trade, before TP1? → Did price hit stop (exit) or TP1 (sell 40%, stop → entry)?
3. In trade, after TP1? → Raise stop to `highest high − 4×ATR` if higher. Exit if hit.
4. Background turned red? → Sell everything now.
5. Down 4% this month? → Sell everything, stop until next month.
6. None of the above? → **Do nothing. Close the app.**

---

## 8. The economic calendar (FOMC / CPI) — what to do with it

Backtested conclusion: **skipping trades before FOMC or CPI loses money**
(every blackout window tested reduced profit), and BTC's direction on CPI days
is statistically random. So the calendar changes *nothing mechanical*. Use it
only to manage yourself:

- Check once a week: FOMC decisions (~8/year, 14:00 ET) at
  federalreserve.gov/monetarypolicy/fomccalendars.htm, CPI releases (monthly,
  08:30 ET) at bls.gov/schedule/news_release/cpi.htm.
- On event days expect violent 4h candles and stop wick-throughs. That is
  normal. Do not panic-close the runner mid-candle, do not chase the spike,
  do not "get flat to be safe" — every decision still happens at candle close
  per the rules above.
- If your stop is hit during an event candle, that's the system working:
  the loss is capped exactly as designed.

## 9. Position sizing (v5.2 recommendation)

Risk **3–5% of your account per trade** (the backtest's own risk was ~5%).
At 5% risk a $1,000 account made ~$1,350 over the 3 tested years but drew
down −24% at the worst point — you must be able to sit through that.
1–2% risk halves the pain and roughly halves the profit. **20% risk was
tested and rejected:** the same trade history contains a 6-loss streak that
turns $1,000 into $262, and starting at a bear top draws down −60%. High
leverage (12x) is never actually used by this system — at 5% risk the
position peaks at ~3.4x notional. Full numbers: `IMPROVEMENT_REPORT.md`.

---

## 10. The short sleeve (v6) — earning in bear markets

The long engine sits flat in bear markets. The v6 sleeve is a second, fully
mechanical position that runs **only** then. It needs a futures account
(Binance USDT-M) because it sells short. Everything happens on 4h closes,
same as always.

**WHEN TO SHORT — both must be true on a 4h close (maroon background + SHORT triangle):**
- `close < SMA200 − 0.5 × ATR(14)` (clearly below the red line, not just touching), AND
- `EMA50 < EMA200`

This can never overlap with the long regime — you are never long and short
at once, and no leverage is used.

**HOW MUCH TO SHORT — size is the risk control (there is NO stop-loss):**

    short notional = 75% × min(1, 40% / realized_vol) × account equity

where realized_vol is the annualized volatility of 4h returns over the last
48 bars (~8 days). The status table prints the current target % for you.
Worked example: equity $1,000, realized vol 60%/yr → scale = 40/60 = 0.67 →
short 0.75 × 0.67 × $1,000 = **$500 notional** (0.0083 BTC at $60,000).
In a calm grinding bear you'll be ~75% short; in a violent crash the formula
automatically cuts the size — that's the protection.

**MANAGING THE SHORT:**
- Re-check the target size at each 4h close. Only adjust if it differs from
  your actual position by **more than ~20%** (avoids fee churn). The script
  fires ADD/REDUCE alerts for this.
- **Do NOT place a price stop-loss.** Every stopped-short variant was
  backtested and loses — bear rallies exist to whipsaw stops. The sleeve
  rides through rallies at controlled size. If a rally breaks the regime,
  the exit rule below fires anyway.

**WHEN TO COVER — either one:**
| # | Cover rule | What you do |
|---|---|---|
| 1 | Deep-bear condition fails on a 4h close (price closes back above SMA200 − 0.5×ATR, or EMA50 crosses above EMA200) | Buy back the whole short at the next open |
| 2 | **Sleeve breaker:** the short has lost **4% of account equity** within this calendar month | Cover everything, no new shorts until the 1st |

**What to expect, honestly (from the 3-year backtest):** the sleeve made the
bear year +31.7% while holders lost 41%, but in choppy sideways periods it
takes small losses — that's the price of insurance, and the monthly cap
keeps each bad month single-digit. The sleeve weight (75%) is the dial:
50% = smoothest ride, 100% = maximum bear profit, monotone in between.
