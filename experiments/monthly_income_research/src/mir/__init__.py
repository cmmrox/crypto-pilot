"""Monthly-income strategy research for BTCUSDT perpetual (research only).

Nothing in this package connects to an account, places orders, or is imported by
the production backend. Decisions are taken on closed 4h candles and executed at
the next 4h open; protective orders are evaluated on 1h bars.
"""
