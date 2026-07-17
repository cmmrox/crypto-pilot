"""Generate the CryptoPilot business-solution architecture diagram (SVG + PDF)."""
import html

W, H = 1440, 1050
parts = []


def rect(x, y, w, h, fill, stroke, rx=8, dash=None, sw=1.5):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=14, fill="#1a2733", weight="normal", anchor="start", family="Helvetica"):
    parts.append(f'<text x="{x}" y="{y}" font-family="{family},Arial,sans-serif" '
                 f'font-size="{size}" fill="{fill}" font-weight="{weight}" '
                 f'text-anchor="{anchor}">{html.escape(s)}</text>')


def lines(x, y, items, size=12, fill="#3d5266", lh=17, anchor="start"):
    for i, s in enumerate(items):
        text(x, y + i * lh, s, size=size, fill=fill, anchor=anchor)


def arrow(x1, y1, x2, y2, color="#5a6b7a", w=2, dash=None, label=None, lx=None, ly=None, lcolor=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                 f'stroke-width="{w}" marker-end="url(#ah)"{d}/>')
    if label:
        text(lx if lx is not None else (x1 + x2) / 2,
             ly if ly is not None else (y1 + y2) / 2 - 6,
             label, size=11, fill=lcolor or "#5a6b7a", anchor="middle")


def box(x, y, w, h, title, sub, fill, stroke, tcolor, scolor, tsize=14):
    rect(x, y, w, h, fill, stroke)
    text(x + 14, y + 24, title, size=tsize, fill=tcolor, weight="bold")
    lines(x + 14, y + 44, sub, size=11.5, fill=scolor, lh=16)


# ---------------- canvas ----------------
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif">')
parts.append('<defs><marker id="ah" markerWidth="9" markerHeight="7" refX="8" refY="3.5" '
             'orient="auto"><polygon points="0 0, 9 3.5, 0 7" fill="#5a6b7a"/></marker></defs>')
rect(0, 0, W, H, "#ffffff", "#ffffff", rx=0)

text(40, 42, "CryptoPilot — Business Solution Diagram", size=26, weight="bold", fill="#0c2a45")
text(40, 66, "Automated BTCUSDT trading of Trend Rider v6 (long + short sleeve) on Binance USDT-M · Python + FastAPI + PostgreSQL · v1.1 · 17 Jul 2026",
     size=13, fill="#5a6b7a")

# ---------------- owner band ----------------
box(40, 92, 320, 78, "Owner — web browser", ["Controls and monitors everything", "from the dashboard (HTTPS + JWT)"],
    "#e8f0fa", "#2a78d6", "#0c447c", "#185fa5")
box(1080, 92, 320, 78, "Owner — phone (SMS)", ["Receives every event: trade open /", "close, bot start / stop, breaker, errors"],
    "#fdf3e2", "#eda100", "#633806", "#854f0b")

# ---------------- presentation / control ----------------
box(40, 210, 320, 110, "React dashboard",
    ["Start / Stop / kill-switch button", "Settings: DEMO or LIVE account, risk %",
     "Live position, equity curve, trade history", "Monthly P&L + daily news briefing"],
    "#e8f0fa", "#2a78d6", "#0c447c", "#185fa5")
box(420, 210, 300, 110, "FastAPI backend",
    ["JWT auth · REST + WebSocket push", "Bot lifecycle commands (start / stop)",
     "Environment switch guard (bot must", "be stopped + confirmation dialog)"],
    "#e8f0fa", "#2a78d6", "#0c447c", "#185fa5")
box(1080, 210, 320, 88, "Notifier service",
    ["Sends SMS through notify.lk gateway", "Template per event type; every SMS", "also logged to the events table"],
    "#fdf3e2", "#eda100", "#633806", "#854f0b")

arrow(200, 170, 200, 210)
arrow(360, 265, 420, 265)
arrow(1240, 210, 1240, 170, label="SMS", lx=1258, ly=194, color="#ba7517")

# ---------------- trading core container ----------------
rect(40, 360, 1000, 300, "#f4f8f6", "#1d9e75", rx=12, dash="7 5", sw=2)
text(56, 386, "Trading core — 24/7 bot service (runs while started; state survives restarts)",
     size=15, fill="#085041", weight="bold")

box(64, 410, 180, 120, "Scheduler",
    ["Wakes on every 4h", "candle close (UTC)", "News cron · health", "checks · reconnects"],
    "#ffffff", "#1d9e75", "#085041", "#0f6e56")

box(282, 402, 260, 140, "Strategy plugin  (swappable)",
    ["Active: Trend Rider v6", "· Long engine (v5.2 rules)", "· Short sleeve (deep bear, vol-sized)",
     "Speaks only Intents: EnterLong,", "EnterShort, MoveStop, ExitAll, Halt"],
    "#eeedfe", "#534ab7", "#26215c", "#3c3489")
text(292, 556, "Also registered: v5.2 long-only · any future strategy — zero changes elsewhere",
     size=10.5, fill="#534ab7")

box(580, 410, 210, 120, "Risk & sizing engine",
    ["Risk % of equity · vol targeting", "Leverage cap (hard max 3x)", "4% monthly breakers (long", "and short sleeve, separate)"],
    "#ffffff", "#1d9e75", "#085041", "#0f6e56")

box(828, 410, 190, 120, "Execution engine",
    ["Order placement, fills,", "lot-size / min-notional", "rounding, retries,", "account reconciliation"],
    "#ffffff", "#1d9e75", "#085041", "#0f6e56")

arrow(244, 470, 282, 470)
arrow(542, 470, 580, 470, label="intents", lx=561, ly=458)
arrow(790, 470, 828, 470, label="orders", lx=809, ly=458)
arrow(570, 320, 570, 360, label="start / stop / status", lx=650, ly=344)

# events to notifier
arrow(1040, 470, 1080, 300, color="#ba7517")
text(945, 336, "events: trade open / close · start / stop · breaker · error",
     size=11, fill="#854f0b", anchor="end")

# ---------------- AI news lane ----------------
rect(1080, 360, 320, 300, "#f7f0f5", "#d4537e", rx=12, dash="7 5", sw=2)
text(1096, 386, "AI news agent — isolated module", size=15, fill="#72243e", weight="bold")
text(1096, 404, "(read-only context; no access to trading or keys)", size=11, fill="#993556")

box(1100, 418, 280, 64, "1 · Collect",
    ["Crypto RSS + macro headlines +", "FOMC / CPI economic calendar"],
    "#ffffff", "#d4537e", "#72243e", "#993556")
box(1100, 500, 280, 64, "2 · Summarise (Claude API)",
    ["Daily briefing: 5–8 market-relevant", "bullets, BTC-volatility flags"],
    "#ffffff", "#d4537e", "#72243e", "#993556")
box(1100, 582, 280, 64, "3 · Publish briefing",
    ["Stored in DB → shown on dashboard", "with source links + event dates panel"],
    "#ffffff", "#d4537e", "#72243e", "#993556")
arrow(1240, 482, 1240, 500)
arrow(1240, 564, 1240, 582)

# ---------------- database ----------------
box(40, 700, 1000, 96, "PostgreSQL — single source of truth",
    ["settings (active environment DEMO | LIVE, active strategy, risk %) · api_credentials (AES-GCM encrypted) · strategies · bot_runs",
     "candles · trades · orders · equity snapshots · events (full audit incl. every SMS) · news_items · briefings   — all timestamps UTC, numeric(20,8)"],
    "#f1efe8", "#5f5e5a", "#2c2c2a", "#444441")
arrow(540, 660, 540, 700, label="every decision, order, fill, event persisted", lx=700, ly=684)
arrow(1150, 660, 1060, 736, color="#993556", label="briefings", lx=1122, ly=690, lcolor="#993556")
parts.append('<line x1="200" y1="320" x2="200" y2="700" stroke="#2a78d6" stroke-width="1.5" stroke-dasharray="3 5" marker-end="url(#ah)"/>')
text(72, 648, "dashboard reads history / equity / news", size=10.5, fill="#2a78d6")

# ---------------- external APIs ----------------
text(40, 848, "External services", size=15, fill="#0c2a45", weight="bold")
box(40, 862, 300, 92, "Binance USDT-M — DEMO (testnet)",
    ["Phase 1: all trading validated here first.", "Own API key pair, stored per environment."],
    "#e8f0fa", "#2a78d6", "#0c447c", "#185fa5")
box(380, 862, 300, 92, "Binance USDT-M — LIVE",
    ["Phase 2: enabled from Settings only after", "DEMO sign-off. Withdrawal permission is", "NEVER granted to the API key."],
    "#fcebeb", "#e24b4a", "#791f1f", "#a32d2d")
box(720, 862, 210, 92, "notify.lk",
    ["SMS gateway (Sri Lanka).", "HTTP API, sender ID,", "delivery status logged."],
    "#fdf3e2", "#eda100", "#633806", "#854f0b")
box(970, 862, 200, 92, "Claude API",
    ["News summarisation", "(claude-haiku-4-5;", "sonnet configurable)."],
    "#f7f0f5", "#d4537e", "#72243e", "#993556")
box(1210, 862, 190, 92, "RSS / calendar feeds",
    ["CoinDesk, CoinTelegraph,", "macro headlines,", "FOMC / CPI dates."],
    "#f7f0f5", "#d4537e", "#72243e", "#993556")

arrow(900, 530, 900, 560)
parts.append('<line x1="900" y1="560" x2="900" y2="620" stroke="#5a6b7a" stroke-width="2"/>')
parts.append('<line x1="900" y1="620" x2="220" y2="620" stroke="#5a6b7a" stroke-width="2" stroke-dasharray="4 4"/>')
arrow(220, 620, 190, 862, label="account data + orders (active environment only)", lx=420, ly=642)
arrow(900, 620, 530, 862, dash="4 4")
# notifier -> notify.lk (routed through the corridor between core and AI lane)
parts.append('<line x1="1150" y1="298" x2="1060" y2="340" stroke="#ba7517" stroke-width="2"/>')
parts.append('<line x1="1060" y1="340" x2="1060" y2="838" stroke="#ba7517" stroke-width="2"/>')
arrow(1060, 838, 900, 862, color="#ba7517")
# summarise -> Claude API (outbound call); RSS feeds -> collect (fetch)
arrow(1100, 545, 1050, 862, color="#993556")
arrow(1330, 862, 1330, 665, color="#993556", label="fetch", lx=1352, ly=770, lcolor="#993556")

# rollout strip
rect(40, 970, 1360, 64, "#eaf3de", "#639922", rx=8)
text(60, 996, "Rollout: 1) DEMO (testnet) account for 4+ weeks — results must match backtest behaviour  →  2) owner sign-off  →  3) switch to LIVE in Settings (bot stopped, confirmed, small risk % first).",
     size=12.5, fill="#27500a")
text(60, 1016, "Start / Stop is available at any moment from the dashboard; the kill-switch flattens all positions and halts the bot instantly. Withdrawal permission is never granted to any API key.",
     size=12.5, fill="#27500a")

parts.append("</svg>")

svg = "\n".join(parts)
with open("CryptoPilot_Solution_Diagram.svg", "w") as f:
    f.write(svg)

import fitz
doc = fitz.open("CryptoPilot_Solution_Diagram.svg")
pdf = fitz.open()
page = pdf.new_page(width=W * 0.72, height=H * 0.72)
pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
page.insert_image(page.rect, pixmap=pix)
pdf.save("CryptoPilot_Solution_Diagram.pdf")
print("wrote CryptoPilot_Solution_Diagram.svg / .pdf")
