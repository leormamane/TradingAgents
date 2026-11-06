"""A scripted run for trying the office without an API key. The text is sample
copy, not analysis, and says so."""

import time

NOTE = "\n\n_(Demo mode: sample text, not a real analysis.)_"


def play(params: dict, emit) -> None:
    t = params["ticker"].strip().upper() or "NVDA"
    analysts = params["analysts"] or ["market", "social", "news", "fundamentals"]
    pause = lambda s: time.sleep(s)

    emit({"type": "log", "text": f"Demo run for {t} on {params['date']}. No model is called."})
    for a in analysts:
        emit({"type": "status", "agent": a, "state": "working"})
    pause(1.2)

    tools = {"market": ["get_stock_data", "get_indicators"],
             "social": ["get_social_sentiment"],
             "news": ["get_news", "get_global_news"],
             "fundamentals": ["get_fundamentals", "get_balance_sheet"]}
    for i in range(2):
        for a in analysts:
            if i < len(tools.get(a, [])):
                emit({"type": "tool", "agent": a, "name": tools[a][i]})
                pause(0.5)

    reports = {
        "market": f"## {t} technicals\n\nPrice is above its 50-day average and RSI sits near 61, "
                  "so momentum is positive but not stretched. MACD crossed up last week.",
        "social": f"## Sentiment\n\nChatter about {t} is mostly upbeat, with some worry about valuation.",
        "news": "## News & macro\n\nNo company-specific shocks this week. Rate expectations are steady.",
        "fundamentals": f"## Fundamentals\n\nRevenue growth remains strong and margins are wide; "
                        "the multiple is high relative to peers.",
    }
    for a in analysts:
        pause(1.0)
        emit({"type": "say", "agent": a, "text": reports[a] + NOTE})
        emit({"type": "status", "agent": a, "state": "done"})

    turns = [
        ("bull", "bear", "Growth and momentum both point up. The trend is our friend here."),
        ("bear", "research_manager", "The valuation already prices in perfection. One miss and it gaps down."),
    ]
    emit({"type": "status", "agent": "bull", "state": "working"})
    for who, nxt, line in turns:
        pause(2.0)
        emit({"type": "say", "agent": who, "text": line + NOTE})
        emit({"type": "status", "agent": who, "state": "idle"})
        emit({"type": "status", "agent": nxt, "state": "working"})

    pause(2.0)
    emit({"type": "status", "agent": "bull", "state": "done"})
    emit({"type": "status", "agent": "bear", "state": "done"})
    emit({"type": "say", "agent": "research_manager",
          "text": "**Recommendation: Overweight.** The bull case is better supported, "
                  "but size it with the valuation risk in mind." + NOTE})
    emit({"type": "status", "agent": "research_manager", "state": "done"})
    emit({"type": "status", "agent": "trader", "state": "working"})

    pause(2.0)
    emit({"type": "say", "agent": "trader",
          "text": "**Action: Buy.** Scale in over three sessions, stop-loss 8% below entry." + NOTE})
    emit({"type": "status", "agent": "trader", "state": "done"})

    risk = [
        ("aggressive", "conservative", "Go full size now. Waiting costs us the move."),
        ("conservative", "neutral", "Half size at most. Earnings are three weeks out."),
        ("neutral", "portfolio_manager", "Scale in as planned, keep the stop. That balances both."),
    ]
    emit({"type": "status", "agent": "aggressive", "state": "working"})
    for who, nxt, line in risk:
        pause(1.8)
        emit({"type": "say", "agent": who, "text": line + NOTE})
        emit({"type": "status", "agent": who, "state": "idle"})
        emit({"type": "status", "agent": nxt, "state": "working"})

    pause(2.2)
    for a in ("aggressive", "conservative", "neutral"):
        emit({"type": "status", "agent": a, "state": "done"})
    emit({"type": "say", "agent": "portfolio_manager",
          "text": f"**Final rating: Overweight** on {t}. Approved with the trader's scaling plan." + NOTE})
    emit({"type": "status", "agent": "portfolio_manager", "state": "done"})
    emit({"type": "decision", "rating": "Overweight", "ticker": t, "date": params["date"],
          "report": None, "demo": True})
