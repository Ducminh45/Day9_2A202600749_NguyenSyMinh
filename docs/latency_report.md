# Stage 5 Latency Report

`test_client.py` now prints:

- Discovery latency: time to fetch the Customer Agent card.
- A2A request latency: time from `send_message()` to final response.
- Total client latency: end-to-end client runtime.

## Baseline

Run the full system, then:

```bash
uv run python test_client.py
```

Record the `A2A request latency` line as the baseline for one question.

## Optimization

The proposed latency reduction is keyword-based fast routing in `law_agent/graph.py`.
It skips the Law Agent router LLM call and directly sets `needs_tax` and
`needs_compliance` from the question text.

Start the Law Agent with:

```bash
FAST_ROUTING=1 uv run python -m law_agent
```

Then run:

```bash
uv run python test_client.py
```

Compare the new `A2A request latency` against the baseline.

## Trade-off

Fast routing reduces latency by removing one LLM call, but it is less flexible
than semantic LLM routing. For production, use keyword routing for common
high-confidence cases and fall back to LLM routing when no keyword matches.
