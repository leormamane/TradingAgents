# Trading Office

A blocky 3D office that shows a TradingAgents run live. Each agent sits at a desk,
types while it works, and says what it found in a speech bubble. The Portfolio
Manager announces the final rating at the end.

```bash
source .venv/bin/activate          # the environment TradingAgents is installed in
python -m office.server            # then open http://localhost:8765
```

- Keys come from your environment or `.env`, the same as the CLI (e.g. `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`).
- OpenRouter: the model boxes list its newest models live; any ID such as `anthropic/claude-sonnet-5` also works.
- **Demo mode** plays a scripted run with sample text. It needs no key and costs nothing.
- Click a worker, a bubble or a feed entry to read the full text. **Full report** opens the saved HTML report.
- Uses only the standard library on top of TradingAgents. Three.js, marked and DOMPurify are bundled in `static/vendor/`, so the page works offline.
- Only one run at a time.

## Cost meter and daily limit

The right panel shows what the current run has cost and today's total against your
daily limit. Click it for a table of recent runs. Every model call is priced by the
model that made it, so a cheap quick model and a pricier deep model are counted right.

```
OFFICE_DAILY_LIMIT_USD=10     # default 10; "off" for no limit
```

- Before a run: refused if today's limit is spent, or if the run's estimated cost
  (about $1.35 with Sonnet 5.5 + Opus 5.5, $0.25 with Haiku 5.5 + Sonnet 5.5) would not fit.
- During a run: checked before every model call, so a run that reaches the limit is
  stopped right there. A day can go over by at most one call.
- Every run, finished or stopped, is written to `~/.tradingagents/office/spend.jsonl`.
- Prices: Claude list prices are built in, OpenRouter's come from OpenRouter, Ollama is
  free. For other models, add `office/prices.json`, in dollars per million tokens:
  `{"gpt-6-luna": {"input": 0.5, "output": 2}}`. A model with no price shows its tokens
  and a "+?" on the cost, and the limit can't count it.
- These are list prices; your provider's bill is the final word.

## Alpaca paper trading

After a real run, the result banner shows the order the rating calls for, and a
**Place paper order** button. Nothing is sent until you click it. It is paper only:
the address is fixed to Alpaca's paper API, so it cannot touch real money.

1. Make a free account at alpaca.markets, open **Paper Trading**, and generate API keys.
2. Add them to `.env` and restart the office:
   ```
   APCA_API_KEY_ID=PK...
   APCA_API_SECRET_KEY=...
   ```
3. Optional limits (defaults shown):
   ```
   OFFICE_MAX_POSITION_PCT=5     # a full Buy position, as % of account equity
   OFFICE_MAX_ORDER_USD=10000    # most one order can be worth
   ```

How a rating becomes an order (plain rules in `broker.py`, not the model):

| Rating | Order |
|---|---|
| Buy | Build up to the full position (5% of equity) |
| Overweight | Build up to 60% of the full position |
| Hold | Nothing |
| Underweight | Trim down to 30% of the full position; never buys |
| Sell | Close the position |

Long only (never shorts), whole shares, market orders. A buy is capped by your cash and
the per-order limit. Buy and Overweight never sell; Underweight never buys. A stock with
an open order is skipped, each decision can be traded once, demo runs can't be traded,
and if the order changed since you saw it you're asked to confirm again. Orders sent while
the market is closed fill at the next open.

With **Agents see my paper holdings** on, the run is given your paper cash and positions,
so the trader, risk team and portfolio manager reason about what you actually hold.

Tests: `python -m pytest office -q` (Alpaca and the models are faked; no network).
