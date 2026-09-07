"""Public failure descriptions are allowlisted; exception text never crosses HTTP."""

FAILURES = {
    "WORKER_FAILED": "Worker failed; inspect the correlated job log",
    "TRADE_ID_GAP": "Binance trade archive contains a gap or duplicate trade ID; verification rejected",
    "TRADE_OHLC_MISMATCH": "Actual trade prices do not reconcile with the Binance candle; verification rejected",
    "FUNDING_MARK_MISSING": "Actual historical funding mark prices are missing; trade verification cannot proceed",
    "DATA_INTEGRITY_FAILED": "The downloaded or cached Binance archive checksum failed",
    "REPLAY_TIMEOUT": "Replay exceeded the configured execution budget",
}


def failure_code(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "REPLAY_TIMEOUT"
    known = {
        "Trade ID gap or duplication": "TRADE_ID_GAP",
        "Actual trade OHLC does not reconcile with Binance candle": "TRADE_OHLC_MISMATCH",
        "Trade replay requires funding mark-price coverage; Binance returned missing marks": "FUNDING_MARK_MISSING",
        "Trade replay requires actual funding mark prices": "FUNDING_MARK_MISSING",
        "Binance archive checksum mismatch": "DATA_INTEGRITY_FAILED",
        "Cached trade archive integrity failed": "DATA_INTEGRITY_FAILED",
    }
    return known.get(str(error), "WORKER_FAILED")
