"""Trading Office: a blocky 3D office that shows a TradingAgents run as it happens.

Run from the repository root, inside the environment TradingAgents is installed in:

    python -m office.server            # http://localhost:8765
    python -m office.server --port 9000 --host 0.0.0.0

Uses only the standard library on top of TradingAgents itself. API keys are read
from the environment or a .env file, exactly like the CLI. Demo mode plays a
scripted run with sample text and needs no key.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from office import broker, demo

STATIC = Path(__file__).parent / "static"

ANALYST_REPORTS = {
    "market_report": "market",
    "sentiment_report": "social",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
}
RISK_KEYS = {
    "aggressive_history": "aggressive",
    "conservative_history": "conservative",
    "neutral_history": "neutral",
}
# Which analyst a tool call belongs to, by name, for the "on the phone" bubble.
TOOL_HINTS = [
    (("indicator", "stock_data", "price", "ohlcv"), "market"),
    (("fundament", "balance", "cashflow", "income", "insider", "filing", "sec"), "fundamentals"),
    (("social", "sentiment", "stocktwits", "reddit"), "social"),
    (("news", "macro", "fred"), "news"),
]

PROVIDERS = ["openai", "anthropic", "google", "xai", "deepseek", "openrouter", "ollama",
             "mistral", "groq", "qwen", "glm", "minimax", "kimi", "nvidia", "azure",
             "chatgpt", "openai_compatible"]

_run_lock = threading.Lock()
_reports: dict[str, Path] = {}
# Real decisions by id. Only these can become paper orders; demo ratings never do.
_decisions: dict[str, dict] = {}


def tool_owner(name: str) -> str | None:
    lowered = name.lower()
    for words, agent in TOOL_HINTS:
        if any(w in lowered for w in words):
            return agent
    return None


_openrouter_cache: tuple[float, list] = (0.0, [])


def openrouter_models(limit: int = 40) -> list[dict]:
    """OpenRouter's newest models from the mainstream labs, listed live like the CLI does.

    Cached for ten minutes. Any model ID still works when typed in by hand."""
    global _openrouter_cache
    fetched_at, models = _openrouter_cache
    if time.time() - fetched_at < (600 if models else 60):
        return models
    import requests
    from cli.prompts import _OPENROUTER_MAINSTREAM
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
        resp.raise_for_status()
        data = sorted(resp.json().get("data", []), key=lambda m: m.get("created") or 0, reverse=True)
    except Exception as exc:
        print(f"Could not list OpenRouter models: {exc}")
        _openrouter_cache = (time.time(), [])  # don't retry on every page load
        return []
    main = [m for m in data if not m["id"].startswith("~")
            and m["id"].split("/", 1)[0] in _OPENROUTER_MAINSTREAM]
    models = [{"label": m.get("name") or m["id"], "value": m["id"]} for m in (main or data)[:limit]]
    _openrouter_cache = (time.time(), models)
    return models


def office_config() -> dict:
    """What the page needs to build its form: providers, models, which keys are set."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

    providers = []
    for p in PROVIDERS:
        env = get_api_key_env(p)
        if p == "openrouter":
            quick = deep = openrouter_models()
        elif p in MODEL_OPTIONS:
            quick = [{"label": l, "value": v} for l, v in MODEL_OPTIONS[p]["quick"]]
            deep = [{"label": l, "value": v} for l, v in MODEL_OPTIONS[p]["deep"]]
        else:
            quick = deep = []  # any model ID; typed into the box
        providers.append({
            "id": p,
            "key_env": env,
            # A local OpenAI-compatible server needs no key.
            "key_set": env is None or p == "openai_compatible" or bool(os.environ.get(env)),
            "quick": quick,
            "deep": deep,
        })
    return {
        "providers": providers,
        "default_provider": DEFAULT_CONFIG.get("llm_provider"),
        "default_quick": DEFAULT_CONFIG.get("quick_think_llm"),
        "default_deep": DEFAULT_CONFIG.get("deep_think_llm"),
    }


def live_run(params: dict, emit) -> None:
    """Run TradingAgents for real and translate its stream into office events."""
    from cli.models import AnalystType
    from cli.prompts import detect_asset_type, filter_analysts_for_asset_type
    from tradingagents.agents.rating import run_rating
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker = params["ticker"].strip().upper()
    date = params["date"]
    asset_type = detect_asset_type(ticker)
    wanted = [a for a in params["analysts"] if a in {t.value for t in AnalystType}]
    analysts = [a.value for a in filter_analysts_for_asset_type(
        [AnalystType(a) for a in wanted], asset_type)]
    if not analysts:
        raise ValueError("Pick at least one analyst.")

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = params["provider"]
    if params.get("quick"):
        config["quick_think_llm"] = params["quick"]
    if params.get("deep"):
        config["deep_think_llm"] = params["deep"]
    config["max_debate_rounds"] = params["depth"]
    config["max_risk_discuss_rounds"] = params["depth"]

    emit({"type": "log", "text": f"Booting the office for {ticker} on {date} "
          f"({config['llm_provider']}: {config['quick_think_llm']} / {config['deep_think_llm']})"})
    graph = TradingAgentsGraph(analysts, config=config, debug=False)
    portfolio = None
    if params.get("use_book") and broker.configured():
        try:
            portfolio = broker.portfolio_context(broker.Alpaca())
            held = portfolio.position_in(ticker)
            emit({"type": "log", "text": "Agents see your Alpaca paper account: "
                  f"${portfolio.cash:,.0f} cash, "
                  f"{f'{held.quantity:g} {ticker} held' if held else f'no {ticker} held'}."})
        except broker.BrokerError as exc:
            emit({"type": "log", "text": f"Could not read the paper account, running without it: {exc}"})
    init_state = graph.create_run_state(ticker, date, asset_type.value, portfolio)
    args = graph.propagator.get_graph_args()

    for a in analysts:
        emit({"type": "status", "agent": a, "state": "working"})

    seen: dict[str, str] = {}
    final_state: dict = {}
    msg_ids: set = set()
    analysts_left = set(analysts)
    turns = {"bull": 0, "bear": 0}

    def new_text(key: str, text: str) -> str:
        """The part of an accumulating history string not shown yet."""
        old = seen.get(key, "")
        seen[key] = text
        return text[len(old):].strip() if text.startswith(old) else text.strip()

    for messages, chunk in graph.stream_run(init_state, **args):
        for m in messages:
            mid = getattr(m, "id", None)
            if mid in msg_ids:
                continue
            if mid:
                msg_ids.add(mid)
            for call in getattr(m, "tool_calls", None) or []:
                name = call["name"] if isinstance(call, dict) else call.name
                emit({"type": "tool", "agent": tool_owner(name), "name": name})
        if not chunk:
            continue
        final_state.update(chunk)

        for key, agent in ANALYST_REPORTS.items():
            text = chunk.get(key)
            if text and seen.get(key) != text:
                seen[key] = text
                emit({"type": "say", "agent": agent, "text": text})
                emit({"type": "status", "agent": agent, "state": "done"})
                analysts_left.discard(agent)
                if not analysts_left:
                    emit({"type": "status", "agent": "bull", "state": "working"})

        debate = chunk.get("investment_debate_state") or {}
        for key, agent, other in (("bull_history", "bull", "bear"), ("bear_history", "bear", "bull")):
            text = debate.get(key) or ""
            if text and (delta := new_text(key, text)):
                emit({"type": "say", "agent": agent, "text": delta})
                emit({"type": "status", "agent": agent, "state": "idle"})
                turns[agent] += 1
                # Each side speaks once per round; after the last bear turn the manager rules.
                if agent == "bear" and turns["bear"] >= config["max_debate_rounds"]:
                    emit({"type": "status", "agent": "research_manager", "state": "working"})
                else:
                    emit({"type": "status", "agent": other, "state": "working"})

        plan = chunk.get("investment_plan")
        if plan and seen.get("investment_plan") != plan:
            seen["investment_plan"] = plan
            for a in ("bull", "bear"):
                emit({"type": "status", "agent": a, "state": "done"})
            emit({"type": "say", "agent": "research_manager", "text": plan})
            emit({"type": "status", "agent": "research_manager", "state": "done"})
            emit({"type": "status", "agent": "trader", "state": "working"})

        trade = chunk.get("trader_investment_plan")
        if trade and seen.get("trader_investment_plan") != trade:
            seen["trader_investment_plan"] = trade
            emit({"type": "say", "agent": "trader", "text": trade})
            emit({"type": "status", "agent": "trader", "state": "done"})
            emit({"type": "status", "agent": "aggressive", "state": "working"})

        risk = chunk.get("risk_debate_state") or {}
        for key, agent in RISK_KEYS.items():
            text = risk.get(key) or ""
            if text and (delta := new_text(key, text)):
                emit({"type": "say", "agent": agent, "text": delta})
                emit({"type": "status", "agent": agent, "state": "idle"})
                turns[agent] = turns.get(agent, 0) + 1
                nxt = {"aggressive": "conservative", "conservative": "neutral"}.get(agent)
                if nxt is None:
                    done_rounds = turns[agent] >= config["max_risk_discuss_rounds"]
                    nxt = "portfolio_manager" if done_rounds else "aggressive"
                emit({"type": "status", "agent": nxt, "state": "working"})

        decision = chunk.get("final_trade_decision")
        if decision and seen.get("final_trade_decision") != decision:
            seen["final_trade_decision"] = decision
            for a in RISK_KEYS.values():
                emit({"type": "status", "agent": a, "state": "done"})
            emit({"type": "say", "agent": "portfolio_manager", "text": decision})
            emit({"type": "status", "agent": "portfolio_manager", "state": "done"})

    graph.record_decision(ticker, date, final_state)
    rating = run_rating(final_state)
    report_id = None
    try:
        path = graph.save_reports(final_state, ticker)
        html = next(Path(path).rglob("complete_report.html"), None)
        if html:
            report_id = uuid.uuid4().hex
            _reports[report_id] = html
    except Exception as exc:  # the decision stands even if saving fails
        emit({"type": "log", "text": f"Report could not be saved: {exc}"})
    decision_id = uuid.uuid4().hex
    _decisions[decision_id] = {"ticker": ticker, "rating": rating, "date": date}
    emit({"type": "decision", "rating": rating, "ticker": ticker, "date": date,
          "decision_id": decision_id, "broker": broker.configured(),
          "report": f"/api/report/{report_id}" if report_id else None})


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingOffice/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._static("index.html")
        if url.path.startswith("/static/"):
            return self._static(url.path[len("/static/"):])
        if url.path == "/api/config":
            return self._send(200, json.dumps(office_config()).encode(), "application/json")
        if url.path == "/api/run":
            return self._run(parse_qs(url.query))
        if url.path == "/api/broker":
            return self._json(200, self._broker_summary())
        if url.path.startswith("/api/report/"):
            path = _reports.get(url.path.rsplit("/", 1)[-1])
            if path and path.exists():
                return self._send(200, path.read_bytes(), "text/html; charset=utf-8")
        self._send(404, b"Not found", "text/plain")

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode(), "application/json")

    @staticmethod
    def _broker_summary() -> dict:
        if not broker.configured():
            return {"configured": False,
                    "reason": "Add APCA_API_KEY_ID and APCA_API_SECRET_KEY (paper keys) to .env and restart."}
        try:
            return broker.summary(broker.Alpaca())
        except broker.BrokerError as exc:
            return {"configured": True, "error": str(exc)}

    def do_POST(self):
        url = urlparse(self.path)
        # Only this page may post: a JSON body with a custom header forces a CORS
        # preflight, which this server never approves, so other sites cannot.
        if (self.headers.get("X-Office") != "1"
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self._json(403, {"error": "Forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 10_000)) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Bad JSON"})
        decision = _decisions.get(str(body.get("decision_id", "")))
        if url.path not in ("/api/broker/plan", "/api/broker/order"):
            return self._json(404, {"error": "Not found"})
        if not decision:
            return self._json(404, {"error": "Unknown decision. Only a finished real run can be traded."})
        try:
            client = broker.Alpaca()
            plan = broker.build_plan(client, decision["ticker"], decision["rating"])
            if url.path == "/api/broker/plan":
                return self._json(200, {"plan": plan.to_dict()})
            # Place only what the person saw: if the plan moved since, show it again.
            if plan.action != body.get("action") or plan.qty != body.get("qty"):
                return self._json(409, {"error": "The order changed since you saw it. Check it and confirm again.",
                                        "plan": plan.to_dict()})
            if plan.action == "none":
                return self._json(400, {"error": plan.reason, "plan": plan.to_dict()})
            if decision.get("order_id"):
                return self._json(409, {"error": "An order was already placed for this decision."})
            order = client.submit(plan.symbol, plan.action, plan.qty,
                                  client_order_id=f"office-{body['decision_id'][:20]}")
            decision["order_id"] = order.get("id")
            return self._json(200, {"order": {"id": order.get("id"), "status": order.get("status"),
                                              "side": order.get("side"), "qty": order.get("qty"),
                                              "symbol": order.get("symbol")},
                                    "plan": plan.to_dict()})
        except broker.BrokerError as exc:
            return self._json(502, {"error": str(exc)})

    def _static(self, name: str):
        path = (STATIC / name).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            return self._send(404, b"Not found", "text/plain")
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                 ".css": "text/css"}.get(path.suffix, "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    def _run(self, q):
        get = lambda k, d="": (q.get(k) or [d])[0]
        params = {
            "ticker": get("ticker", "NVDA") or "NVDA",
            "date": get("date") or time.strftime("%Y-%m-%d"),
            "provider": get("provider", "openai"),
            "quick": get("quick"),
            "deep": get("deep"),
            "analysts": [a for a in get("analysts", "market,social,news,fundamentals").split(",") if a],
            "depth": max(1, min(5, int(get("depth", "1") or 1))),
            "use_book": get("book") == "1",
        }
        is_demo = get("demo") == "1"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        events: queue.Queue = queue.Queue()
        if not _run_lock.acquire(blocking=False):
            events.put({"type": "error", "message": "Another run is already in progress."})
            events.put(None)
        else:
            def work():
                try:
                    (demo.play if is_demo else live_run)(params, events.put)
                except Exception as exc:
                    traceback.print_exc()
                    events.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                finally:
                    _run_lock.release()
                    events.put(None)
            threading.Thread(target=work, daemon=True).start()

        try:
            while True:
                try:
                    ev = events.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                if ev is None:
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    break
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page closed; a live run keeps going and still records its decision


def main():
    ap = argparse.ArgumentParser(description="Trading Office UI for TradingAgents")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    try:
        server = ThreadingHTTPServer((a.host, a.port), Handler)
    except OSError as exc:
        if exc.errno in (48, 98):  # address already in use (macOS, Linux)
            raise SystemExit(
                f"Port {a.port} is already in use. The office may already be running at "
                f"http://{a.host}:{a.port}; otherwise pick another port: "
                f"python -m office.server --port {a.port + 1}")
        raise
    print(f"Trading Office open at http://{a.host}:{a.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
