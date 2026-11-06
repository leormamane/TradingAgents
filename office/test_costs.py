"""Tests for the cost meter and the daily limit. No model is called.

    python -m pytest office/test_costs.py -q
"""

import uuid

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from office import costs, server


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(costs, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(costs, "CUSTOM_PRICES", tmp_path / "prices.json")
    monkeypatch.setenv("OFFICE_DAILY_LIMIT_USD", "10")
    return tmp_path


def call(meter, model, t_in, t_out, cached=0):
    """Feed the meter one model call the way LangChain reports it."""
    rid = uuid.uuid4()
    meter.on_chat_model_start({}, [[]], run_id=rid, invocation_params={"model": model})
    usage = {"input_tokens": t_in, "output_tokens": t_out, "total_tokens": t_in + t_out,
             "input_token_details": {"cache_read": cached}}
    msg = AIMessage(content="ok", usage_metadata=usage)
    meter.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=rid)


def test_claude_prices_and_openrouter_names():
    assert costs.price_for("claude-opus-5-5")["output"] == 20.0
    assert costs.price_for("anthropic/claude-sonnet-5-5")["input"] == 2.0
    assert costs.price_for("anything", "ollama") == {"input": 0.0, "output": 0.0}
    assert costs.price_for("mystery-model") is None


def test_openrouter_live_prices_win():
    costs.set_openrouter_prices([{"id": "x/y", "pricing": {"prompt": "0.000001", "completion": "0.000002"}}])
    assert costs.price_for("x/y") == {"input": 1.0, "output": 2.0}


def test_custom_price_file(ledger):
    (ledger / "prices.json").write_text('{"gpt-6-luna": {"input": 0.5, "output": 2}}')
    assert costs.price_for("gpt-6-luna")["output"] == 2


def test_meter_prices_each_call_by_its_own_model():
    m = costs.RunMeter({}, spent_before=0, limit=None)
    call(m, "claude-sonnet-5-5", 100_000, 10_000)   # $0.20 + $0.10
    call(m, "claude-opus-5-5", 10_000, 5_000)       # $0.04 + $0.10
    assert m.snapshot()["cost"] == pytest.approx(0.44)
    assert m.calls == 2 and m.tokens_in == 110_000


def test_cache_reads_are_cheaper():
    m = costs.RunMeter({}, 0, None)
    call(m, "claude-sonnet-5-5", 100_000, 0, cached=100_000)
    assert m.cost == pytest.approx(0.02)            # $0.20 per M cached instead of $2


def test_unknown_models_are_flagged_not_guessed():
    m = costs.RunMeter({}, 0, None)
    call(m, "mystery-model", 1000, 1000)
    assert m.cost == 0 and m.snapshot()["unpriced"] == ["mystery-model"]


def test_limit_stops_the_next_call():
    m = costs.RunMeter({}, spent_before=9.90, limit=10.0)
    call(m, "claude-opus-5-5", 0, 10_000)           # $0.20 -> $10.10 spent today
    with pytest.raises(costs.LimitReached):
        m.on_chat_model_start({}, [[]], run_id=uuid.uuid4(), invocation_params={"model": "claude-opus-5-5"})


def test_ledger_adds_up_today():
    costs.record({"day": costs.date.today().isoformat(), "cost": 1.25, "ticker": "A", "at": "x"})
    costs.record({"day": "2000-01-01", "cost": 99, "ticker": "B", "at": "y"})
    assert costs.spent_on() == pytest.approx(1.25)
    assert costs.summary()["left"] == pytest.approx(8.75)


def test_limit_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("OFFICE_DAILY_LIMIT_USD", "off")
    assert costs.daily_limit() is None


PARAMS = {"ticker": "NVDA", "date": "2026-11-05", "provider": "anthropic", "quick": "claude-sonnet-5-5",
          "deep": "claude-opus-5-5", "analysts": ["market"], "depth": 1, "use_book": False}


def test_run_refused_when_the_day_is_spent():
    costs.record({"day": costs.date.today().isoformat(), "cost": 10.0, "ticker": "A", "at": "x"})
    with pytest.raises(costs.LimitReached, match="spent"):
        server.live_run(dict(PARAMS), lambda ev: None)


def test_run_refused_when_the_estimate_does_not_fit():
    costs.record({"day": costs.date.today().isoformat(), "cost": 9.5, "ticker": "A", "at": "x"})
    with pytest.raises(costs.LimitReached, match="estimated"):
        server.live_run(dict(PARAMS), lambda ev: None)
