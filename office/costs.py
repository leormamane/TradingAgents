"""What runs cost, and a daily limit that stops them.

Every model call reports its tokens; this prices them by the model that made the
call and adds them up per run. Finished and stopped runs go to a ledger
(~/.tradingagents/office/spend.jsonl), and the day's total is checked against
OFFICE_DAILY_LIMIT_USD before a run starts and after every model call during it.
A run that would cross the limit is stopped right there, so the most a day can go
over is one model call.

Prices are per million tokens. Claude list prices are built in; OpenRouter prices
come from OpenRouter's own model list; Ollama is local and free. Anything else can
be added to office/prices.json:  {"model-id": {"input": 2.0, "output": 10.0}}
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

# USD per million tokens. cache_read is what a prompt-cache hit costs.
CLAUDE_PRICES = {
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cache_read": 0.25},
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}

LEDGER = Path(os.path.expanduser("~/.tradingagents/office/spend.jsonl"))
CUSTOM_PRICES = Path(__file__).parent / "prices.json"

# A rough size for one run, used only to warn before starting (see README for how
# it was estimated): tokens on the quick tier and on the deep tier.
TYPICAL_RUN = {"quick": (300_000, 40_000), "deep": (40_000, 10_000)}

_lock = threading.Lock()
_openrouter: dict[str, dict] = {}


class LimitReached(Exception):
    """Raised inside a run when the next call would go past the daily limit."""


def daily_limit() -> float | None:
    raw = os.environ.get("OFFICE_DAILY_LIMIT_USD", "10").strip().lower()
    if raw in ("", "0", "none", "off"):
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"OFFICE_DAILY_LIMIT_USD must be a number or 'off', got {raw!r}") from exc
    return value if value > 0 else None


def set_openrouter_prices(models: list[dict]) -> None:
    """Keep OpenRouter's own per-token prices from its model list."""
    for m in models:
        p = m.get("pricing") or {}
        try:
            _openrouter[m["id"]] = {"input": float(p["prompt"]) * 1e6, "output": float(p["completion"]) * 1e6}
        except (KeyError, TypeError, ValueError):
            continue


def price_for(model: str, provider: str | None = None) -> dict | None:
    """Price of a model in USD per million tokens, or None if unknown."""
    if not model:
        return None
    if provider == "ollama":
        return {"input": 0.0, "output": 0.0}
    try:
        custom = json.loads(CUSTOM_PRICES.read_text()) if CUSTOM_PRICES.exists() else {}
    except (OSError, ValueError):
        custom = {}
    if model in custom:
        return custom[model]
    if model in _openrouter:
        return _openrouter[model]
    bare = model.split("/", 1)[-1]          # anthropic/claude-sonnet-5-5 -> claude-sonnet-5-5
    for name in (model, bare, bare.replace(".", "-")):
        if name in CLAUDE_PRICES:
            return CLAUDE_PRICES[name]
    return None


def cost_of(price: dict | None, tokens_in: int, tokens_out: int, cache_read: int = 0) -> float | None:
    if price is None:
        return None
    fresh = max(tokens_in - cache_read, 0)
    return (fresh * price["input"] + cache_read * price.get("cache_read", price["input"])
            + tokens_out * price["output"]) / 1e6


def estimate_run(quick: tuple[str, str], deep: tuple[str, str], rounds: int = 1) -> float | None:
    """Rough cost of one run before it starts; None if a price is unknown."""
    scale = 1 + 0.4 * (max(rounds, 1) - 1)
    total = 0.0
    for tier, (provider, model) in (("quick", quick), ("deep", deep)):
        c = cost_of(price_for(model, provider), *TYPICAL_RUN[tier])
        if c is None:
            return None
        total += c * scale
    return total


# ---------------------------------------------------------------- ledger

def spent_on(day: date | None = None) -> float:
    day = day or date.today()
    total = 0.0
    with _lock:
        if not LEDGER.exists():
            return 0.0
        for line in LEDGER.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("day") == day.isoformat():
                total += row.get("cost") or 0.0
    return total


def recent_runs(n: int = 10) -> list[dict]:
    with _lock:
        if not LEDGER.exists():
            return []
        rows = []
        for line in LEDGER.read_text().splitlines()[-n:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows[::-1]


def record(row: dict) -> None:
    with _lock:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps(row) + "\n")


def summary() -> dict:
    limit = daily_limit()
    today = spent_on()
    return {"today": round(today, 4), "limit": limit,
            "left": None if limit is None else round(max(limit - today, 0), 4),
            "recent": recent_runs(8)}


# ---------------------------------------------------------------- the meter

class RunMeter(BaseCallbackHandler):
    """Counts each model call's tokens, prices them, and enforces the daily limit."""

    raise_error = True      # let LimitReached stop the run instead of being logged

    def __init__(self, providers: dict[str, str], spent_before: float, limit: float | None, on_update=None):
        super().__init__()
        self.providers = providers          # model id -> provider, to price each call
        self.spent_before = spent_before
        self.limit = limit
        self.on_update = on_update
        self._lock = threading.Lock()
        self._models: dict[Any, str] = {}
        self.calls = 0
        self.tokens_in = self.tokens_out = self.cache_read = 0
        self.cost = 0.0
        self.unpriced: set[str] = set()
        self.by_model: dict[str, dict] = {}
        self.started = time.time()

    def _check(self):
        if self.limit is not None and self.spent_before + self.cost >= self.limit:
            raise LimitReached(
                f"Daily limit of ${self.limit:,.2f} reached (${self.spent_before + self.cost:,.2f} spent today). "
                "The run was stopped. Raise OFFICE_DAILY_LIMIT_USD in .env to allow more.")

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._check()   # refuse the next call once the day is spent
        params = kwargs.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name") or (serialized or {}).get("kwargs", {}).get("model")
        with self._lock:
            self._models[run_id] = model or ""


    def on_llm_end(self, response, *, run_id, **kwargs):
        usage, model = None, self._models.pop(run_id, "")
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            usage = getattr(msg, "usage_metadata", None)
            meta = getattr(msg, "response_metadata", None) or {}
            model = model or meta.get("model_name") or meta.get("model") or ""
        except (IndexError, TypeError, AttributeError):
            pass
        if not usage:
            return
        t_in = usage.get("input_tokens", 0) or 0
        t_out = usage.get("output_tokens", 0) or 0
        cached = ((usage.get("input_token_details") or {}).get("cache_read") or 0)
        price = price_for(model, self.providers.get(model))
        c = cost_of(price, t_in, t_out, cached)
        with self._lock:
            self.calls += 1
            self.tokens_in += t_in
            self.tokens_out += t_out
            self.cache_read += cached
            row = self.by_model.setdefault(model or "?", {"calls": 0, "in": 0, "out": 0, "cost": 0.0})
            row["calls"] += 1
            row["in"] += t_in
            row["out"] += t_out
            if c is None:
                self.unpriced.add(model or "?")
            else:
                self.cost += c
                row["cost"] += c
        if self.on_update:
            self.on_update(self.snapshot())

    def snapshot(self) -> dict:
        with self._lock:
            return {"calls": self.calls, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                    "cost": round(self.cost, 4), "today": round(self.spent_before + self.cost, 4),
                    "limit": self.limit, "unpriced": sorted(self.unpriced)}

    def ledger_row(self, ticker: str, status: str, rating: str | None = None) -> dict:
        snap = self.snapshot()
        return {"day": date.today().isoformat(), "at": datetime.now().isoformat(timespec="seconds"),
                "ticker": ticker, "status": status, "rating": rating, "cost": snap["cost"],
                "tokens_in": snap["tokens_in"], "tokens_out": snap["tokens_out"], "calls": snap["calls"],
                "seconds": round(time.time() - self.started), "unpriced": snap["unpriced"],
                "by_model": {m: {**v, "cost": round(v["cost"], 4)} for m, v in self.by_model.items()}}
