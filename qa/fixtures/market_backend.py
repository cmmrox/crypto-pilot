"""CI-only public-market fixture; never copied into production images.

Runs real API/auth/storage/backfill code against deterministic REST-shaped data.
It is not Binance reachability or exchange acceptance evidence. Signed requests
and all mutations fail closed. The Compose mount and test-only guards are required.
"""

import time
from decimal import Decimal


def require_test_stack():
    from app.core.config import get_settings

    settings = get_settings()
    database = str(settings.database_url).rsplit("/", 1)[-1]
    if (
        settings.environment != "test"
        or not settings.otp_test_mode
        or not database.endswith("_e2e")
        or settings.live_trading_approved
        or settings.live_key_permissions_verified
    ):
        raise RuntimeError(
            "Synthetic market backend requires isolated OTP-test E2E stack"
        )


async def public_response(self, method, path, *, params=None, signed=False):
    from app.execution.binance_client import BinanceError

    if signed or method != "GET":
        raise BinanceError("CI fixture refuses signed requests and exchange mutations")
    now_ms = int(time.time() * 1000)
    if path == "/fapi/v1/time":
        return {"serverTime": now_ms}
    if path == "/fapi/v1/premiumIndex":
        return {"symbol": "BTCUSDT", "markPrice": "50025", "time": now_ms}
    if path == "/fapi/v1/ticker/24hr":
        return {"symbol": "BTCUSDT", "priceChangePercent": "0.5"}
    if path == "/fapi/v1/klines":
        query = params or {}
        if query.get("symbol") != "BTCUSDT" or query.get("interval") != "4h":
            raise BinanceError("Unsupported CI fixture market")
        step = 4 * 60 * 60 * 1000
        last_closed = (now_ms // step) * step - step
        end = min(int(query.get("endTime", last_closed)), last_closed)
        count = min(int(query.get("limit", 500)), 1500)
        start = max(int(query.get("startTime", end - (count - 1) * step)), 0)
        start = ((start + step - 1) // step) * step
        rows = []
        for opened in range(start, end + 1, step):
            price = Decimal("50000") + Decimal((opened // step) % 120)
            rows.append(
                [
                    opened,
                    str(price),
                    str(price + 100),
                    str(price - 100),
                    str(price + 25),
                    "10",
                    opened + step - 1,
                    "500000",
                    100,
                    "5",
                    "250000",
                    "0",
                ]
            )
            if len(rows) == count:
                break
        return rows
    raise BinanceError("Unsupported CI public-market endpoint")


def install():
    require_test_stack()
    from app.execution.binance_client import BinanceClient

    BinanceClient._request = public_response


if __name__ == "__main__":
    import uvicorn

    install()
    print(
        "CI synthetic public-market fixture enabled; no exchange execution", flush=True
    )
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=1)
