"""Alpaca paper trading for the Trading Office.

Paper only: the endpoint is fixed to Alpaca's paper API and there is no setting
that points it at a live account. Orders are never placed on their own; the page
shows the plan and a person confirms it.

The rating becomes an order by plain rules, not by the model:

    Buy          -> hold the full target position (MAX_POSITION_PCT of equity)
    Overweight   -> hold OVERWEIGHT_FRACTION of the full target
    Hold         -> no order
    Underweight  -> trim to UNDERWEIGHT_FRACTION of the full target (never adds)
    Sell         -> close the position
    REVIEW / ?   -> no order

Long only: it never shorts. Buys are whole shares, and an order is capped by the
cash on hand and by MAX_ORDER_USD. A symbol with an open order is left alone.

Environment (in .env):

    APCA_API_KEY_ID=...        # from the Paper Trading dashboard at alpaca.markets
    APCA_API_SECRET_KEY=...
    OFFICE_MAX_POSITION_PCT=5  # optional, % of equity for a full Buy position
    OFFICE_MAX_ORDER_USD=10000 # optional, cap on one order's value
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass

import requests

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"

OVERWEIGHT_FRACTION = 0.6
UNDERWEIGHT_FRACTION = 0.3


class BrokerError(Exception):
    pass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError as exc:
        raise BrokerError(f"{name} must be a number, got {raw!r}") from exc


def limits() -> dict:
    pct = _env_float("OFFICE_MAX_POSITION_PCT", 5.0)
    cap = _env_float("OFFICE_MAX_ORDER_USD", 10_000.0)
    if not 0 < pct <= 100:
        raise BrokerError("OFFICE_MAX_POSITION_PCT must be between 0 and 100")
    if cap <= 0:
        raise BrokerError("OFFICE_MAX_ORDER_USD must be above 0")
    return {"max_position_pct": pct, "max_order_usd": cap}


def configured() -> bool:
    return bool(os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY"))


class Alpaca:
    """The few paper-API calls the office needs, over plain HTTPS."""

    def __init__(self, key: str | None = None, secret: str | None = None, session=None):
        key = key or os.environ.get("APCA_API_KEY_ID")
        secret = secret or os.environ.get("APCA_API_SECRET_KEY")
        if not (key and secret):
            raise BrokerError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env (paper keys).")
        self.http = session or requests.Session()
        self.http.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})

    def _call(self, method: str, url: str, **kw):
        try:
            r = self.http.request(method, url, timeout=15, **kw)
        except requests.RequestException as exc:
            raise BrokerError(f"Could not reach Alpaca: {exc}") from exc
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or r.text
            except ValueError:
                msg = r.text
            if r.status_code in (401, 403):
                msg = f"{msg} (are these paper-trading keys?)"
            raise BrokerError(f"Alpaca said {r.status_code}: {msg}")
        return r.json() if r.content else None

    def account(self) -> dict:
        return self._call("GET", f"{PAPER_URL}/v2/account")

    def positions(self) -> list[dict]:
        return self._call("GET", f"{PAPER_URL}/v2/positions") or []

    def position(self, symbol: str) -> dict | None:
        return self._call("GET", f"{PAPER_URL}/v2/positions/{symbol}")

    def asset(self, symbol: str) -> dict | None:
        return self._call("GET", f"{PAPER_URL}/v2/assets/{symbol}")

    def open_orders(self, symbol: str | None = None) -> list[dict]:
        params = {"status": "open", "limit": 100}
        if symbol:
            params["symbols"] = symbol
        return self._call("GET", f"{PAPER_URL}/v2/orders", params=params) or []

    def recent_orders(self, limit: int = 20) -> list[dict]:
        return self._call("GET", f"{PAPER_URL}/v2/orders",
                          params={"status": "all", "limit": limit, "direction": "desc"}) or []

    def last_price(self, symbol: str) -> float:
        data = self._call("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest", params={"feed": "iex"})
        price = ((data or {}).get("trade") or {}).get("p")
        if not price:
            raise BrokerError(f"No recent price for {symbol} from Alpaca.")
        return float(price)

    def submit(self, symbol: str, side: str, qty: int, client_order_id: str) -> dict:
        return self._call("POST", f"{PAPER_URL}/v2/orders", json={
            "symbol": symbol, "side": side, "qty": str(qty), "type": "market",
            "time_in_force": "day", "client_order_id": client_order_id,
        })


@dataclass
class Plan:
    symbol: str
    rating: str
    action: str                 # "buy", "sell" or "none"
    qty: int
    price: float | None
    est_value: float
    current_qty: float
    target_qty: int | None
    equity: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def target_fraction(rating: str) -> float | None:
    """Share of the full target position a rating asks for; None means leave it."""
    return {"Buy": 1.0, "Overweight": OVERWEIGHT_FRACTION, "Underweight": UNDERWEIGHT_FRACTION,
            "Sell": 0.0}.get(rating)


def plan_order(symbol: str, rating: str, *, equity: float, cash: float, price: float | None,
               current_qty: float, max_position_pct: float, max_order_usd: float,
               has_open_order: bool = False) -> Plan:
    """The order a rating calls for, under the limits. Pure: no network."""
    symbol = symbol.upper()
    base = dict(symbol=symbol, rating=rating, price=price, current_qty=current_qty, equity=equity)

    def none(reason, target=None):
        return Plan(action="none", qty=0, est_value=0.0, target_qty=target, reason=reason, **base)

    if has_open_order:
        return none(f"{symbol} already has an open order; wait for it to fill or cancel it.")
    frac = target_fraction(rating)
    if frac is None:
        return none("Hold: no change." if rating == "Hold" else f"Rating {rating!r} is not tradeable.")
    if current_qty < 0:
        return none(f"Account is short {symbol}; this tool only trades long positions.")
    if frac == 0.0:
        if current_qty <= 0:
            return none(f"Sell, but no {symbol} is held.", 0)
        qty = math.floor(current_qty)
        if qty < 1:
            return none("Less than one share held.", 0)
        return Plan(action="sell", qty=qty, est_value=round(qty * (price or 0), 2), target_qty=0,
                    reason=f"Sell: close the position ({qty} shares).", **base)
    if not price or price <= 0:
        return none(f"No price for {symbol}.")

    target_value = equity * max_position_pct / 100 * frac
    target_qty = math.floor(target_value / price)
    diff = target_qty - current_qty
    label = f"{rating}: target {target_qty} shares (~${target_qty * price:,.0f}, " \
            f"{max_position_pct * frac:g}% of equity)"

    if rating == "Underweight" and diff > 0:
        return none(f"Underweight, and the position ({current_qty:g} shares) is already at or "
                    f"below the trimmed target of {target_qty}.", target_qty)
    if diff >= 1:
        affordable = math.floor(min(max_order_usd, max(cash, 0)) / price)
        qty = min(math.floor(diff), affordable)
        if qty < 1:
            return none(f"{label}, but cash or the ${max_order_usd:,.0f} order cap allows no shares.", target_qty)
        capped = " (capped by cash or the order limit)" if qty < math.floor(diff) else ""
        return Plan(action="buy", qty=qty, est_value=round(qty * price, 2), target_qty=target_qty,
                    reason=f"{label}. Holding {current_qty:g}, buy {qty}{capped}.", **base)
    if diff <= -1 and rating in ("Buy", "Overweight"):
        return none(f"{label}. Already holding {current_qty:g}, above target; "
                    f"a {rating} rating never sells.", target_qty)
    if diff <= -1:
        qty = min(math.floor(-diff), math.floor(max_order_usd / price)) or 1
        qty = min(qty, math.floor(current_qty))
        return Plan(action="sell", qty=qty, est_value=round(qty * price, 2), target_qty=target_qty,
                    reason=f"{label}. Holding {current_qty:g}, sell {qty}.", **base)
    return none(f"{label}. Already holding {current_qty:g}; no change.", target_qty)


def build_plan(client: Alpaca, symbol: str, rating: str) -> Plan:
    symbol = symbol.upper()
    asset = client.asset(symbol)
    if not asset or not asset.get("tradable") or asset.get("class") != "us_equity":
        return Plan(symbol=symbol, rating=rating, action="none", qty=0, price=None, est_value=0.0,
                    current_qty=0, target_qty=None, equity=0,
                    reason=f"{symbol} is not a US stock Alpaca can trade.")
    acct = client.account()
    if acct.get("trading_blocked") or acct.get("account_blocked"):
        raise BrokerError("The Alpaca paper account is blocked from trading.")
    pos = client.position(symbol)
    current = float(pos["qty"]) if pos else 0.0
    frac = target_fraction(rating)
    price = client.last_price(symbol) if frac not in (None, 0.0) else (
        float(pos["current_price"]) if pos and pos.get("current_price") else None)
    lim = limits()
    return plan_order(symbol, rating, equity=float(acct["equity"]), cash=float(acct["cash"]),
                      price=price, current_qty=current, has_open_order=bool(client.open_orders(symbol)),
                      **lim)


def summary(client: Alpaca) -> dict:
    """Account, positions and recent orders for the page."""
    acct = client.account()
    return {
        "configured": True,
        "equity": float(acct["equity"]),
        "cash": float(acct["cash"]),
        "buying_power": float(acct["buying_power"]),
        "positions": [{"symbol": p["symbol"], "qty": float(p["qty"]),
                       "avg_price": float(p["avg_entry_price"]),
                       "market_value": float(p["market_value"]),
                       "unrealized_pl": float(p["unrealized_pl"])} for p in client.positions()],
        "orders": [{"symbol": o["symbol"], "side": o["side"], "qty": o.get("qty"),
                    "status": o["status"], "filled_avg_price": o.get("filled_avg_price"),
                    "submitted_at": o.get("submitted_at")} for o in client.recent_orders(10)],
        "limits": limits(),
    }


def portfolio_context(client: Alpaca):
    """The paper account as a TradingAgents portfolio, so the agents know what is held."""
    from tradingagents.portfolio import PortfolioContext
    acct = client.account()
    return PortfolioContext.model_validate({
        "cash": float(acct["cash"]),
        "currency": acct.get("currency") or "USD",
        "positions": [{"ticker": p["symbol"], "quantity": float(p["qty"]),
                       "average_price": float(p["avg_entry_price"])} for p in client.positions()],
    })
