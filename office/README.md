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
- Only one run at a time. Research tool only: it places no trades.
