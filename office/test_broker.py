"""Tests for the paper-trading rules and the order endpoint. No network: Alpaca is faked.

    python -m pytest office/test_broker.py -q
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from office import broker, server
from office.broker import plan_order

LIM = dict(max_position_pct=5.0, max_order_usd=10_000.0)


def plan(rating, current=0.0, price=100.0, equity=100_000.0, cash=100_000.0, **kw):
    return plan_order("nvda", rating, equity=equity, cash=cash, price=price, current_qty=current,
                      **{**LIM, **kw})


def test_buy_goes_to_full_target():
    p = plan("Buy")
    assert (p.action, p.qty, p.target_qty, p.symbol) == ("buy", 50, 50, "NVDA")   # 5% of 100k / $100


def test_overweight_is_a_partial_target():
    assert (plan("Overweight").action, plan("Overweight").qty) == ("buy", 30)


def test_buy_tops_up_only_the_difference():
    assert plan("Buy", current=20).qty == 30


def test_buy_or_overweight_never_sells_above_target():
    assert plan("Buy", current=80).action == "none"
    assert plan("Overweight", current=45).action == "none"


def test_hold_and_review_do_nothing():
    assert plan("Hold", current=10).action == "none"
    assert plan("REVIEW").action == "none"


def test_underweight_trims_but_never_adds():
    assert (plan("Underweight", current=40).action, plan("Underweight", current=40).qty) == ("sell", 25)
    assert plan("Underweight", current=0).action == "none"


def test_sell_closes_whole_shares_and_needs_a_position():
    assert (plan("Sell", current=12.7).action, plan("Sell", current=12.7).qty) == ("sell", 12)
    assert plan("Sell").action == "none"


def test_order_cap_and_cash_limit_buys():
    assert plan("Buy", max_order_usd=1_000).qty == 10
    assert plan("Buy", cash=750).qty == 7
    assert plan("Buy", cash=50).action == "none"


def test_short_positions_and_open_orders_are_left_alone():
    assert plan("Sell", current=-5).action == "none"
    assert plan("Buy", has_open_order=True).action == "none"


def test_paper_endpoint_is_fixed():
    assert broker.PAPER_URL == "https://paper-api.alpaca.markets"


# ---------------------------------------------------------------- endpoint

class FakeAlpaca:
    submitted = []

    def __init__(self, *a, **kw):
        pass

    def asset(self, s):
        return {"tradable": True, "class": "us_equity"}

    def account(self):
        return {"equity": "100000", "cash": "100000", "buying_power": "200000"}

    def position(self, s):
        return None

    def open_orders(self, s=None):
        return []

    def last_price(self, s):
        return 100.0

    def submit(self, symbol, side, qty, client_order_id):
        FakeAlpaca.submitted.append((symbol, side, qty))
        return {"id": "o1", "status": "accepted", "side": side, "qty": str(qty), "symbol": symbol}


@pytest.fixture
def office(monkeypatch):
    monkeypatch.setattr(broker, "Alpaca", FakeAlpaca)
    FakeAlpaca.submitted = []
    server._decisions.clear()
    server._decisions["d1"] = {"ticker": "NVDA", "rating": "Buy", "date": "2026-11-05"}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def post(base, path, body, headers=None):
    h = {"Content-Type": "application/json", "X-Office": "1"} if headers is None else headers
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_plan_then_place(office):
    status, data = post(office, "/api/broker/plan", {"decision_id": "d1"})
    assert status == 200 and data["plan"]["qty"] == 50
    status, data = post(office, "/api/broker/order", {"decision_id": "d1", "action": "buy", "qty": 50})
    assert status == 200 and FakeAlpaca.submitted == [("NVDA", "buy", 50)]
    # the same decision cannot be traded twice
    status, _ = post(office, "/api/broker/order", {"decision_id": "d1", "action": "buy", "qty": 50})
    assert status == 409 and len(FakeAlpaca.submitted) == 1


def test_order_must_match_what_was_shown(office):
    status, data = post(office, "/api/broker/order", {"decision_id": "d1", "action": "buy", "qty": 500})
    assert status == 409 and data["plan"]["qty"] == 50 and not FakeAlpaca.submitted


def test_unknown_or_demo_decisions_cannot_trade(office):
    status, _ = post(office, "/api/broker/order", {"decision_id": "nope", "action": "buy", "qty": 50})
    assert status == 404 and not FakeAlpaca.submitted


def test_cross_site_posts_are_refused(office):
    status, _ = post(office, "/api/broker/order", {"decision_id": "d1", "action": "buy", "qty": 50},
                     headers={"Content-Type": "text/plain"})
    assert status == 403 and not FakeAlpaca.submitted
