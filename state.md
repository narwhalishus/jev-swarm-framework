# jev-swarm-framework loop state

## Goal

Turn this repo into a generic Python SDK for real-time swarm experiments with Jev, where offline runs and live sessions are the same experiment, and the three-dress adaptive storefront is the first example app. Done for v1 means:

- the SDK core (multi-role environments, weighted personas, `Session`, site policies, `compare`) runs the three-dress scenario offline;
- it produces the four-way comparison (no offer, fixed rule, single-step Jev, lookahead);
- the viewer shows persona weights, EV per offer and uplift labels.

The rationale lives in `DESIGN.md`.

## Queue

1. **SDK core v1.** Next action: once Bryan approves the API sketch (see Waiting), write `examples/three_dresses.py` as the runnable contract. Then implement `Environment` with roles, `Population` (likelihood weighting, ESS, the "nobody explains the user" trigger), `Session.observe/decide`, the policies `NoOffer`, `Rule`, `SingleStep` and `Lookahead` (wide and shallow by default, depth configurable), and `compare` with frontier-played hidden shoppers.
2. **Port what exists to the new interface.** Next action: move `GraphEnvironment` and the JSON scenarios onto the multi-role `Environment`, replace the per-actor beam runner in `engine.py` with `Session` and policies, then regenerate `examples/live-*` with live Jev and update `examples/latency_probe.py`, which reads the old trace schema.
3. **Jev client.** Next action: reuse the HTTP connection in `transport.py`, which opens a fresh connection per request at about 30 ms of connect and TLS each. Pack batches by Jev's token limits (64k per request; 32k for state plus the longest question) instead of 16 questions or 80 KB, and pin `jev-1.13.0` in experiments.
4. **Self-scoring and spread.** Next action: score each real or simulated action against the mixture prediction with log loss and calibration, against four baselines (no-persona Jev, a single persona, shuffled personas, empirical frequencies). Add behavioral spread (pairwise Jensen–Shannon divergence between persona action distributions at the same state).
5. **Viewer.** Next action: show persona weights over time, EV per candidate offer, uplift labels per persona, and the comparison table.
6. **Clickable mock storefront (approved for the next pass, not this one).** Next action after v1: a small local server over the `Session` API, where Bryan shops and the swarm reacts live.

## Waiting on Bryan

- **Approve or redirect the usage-first API sketch and its four choices.** The developer writes an `Environment` with `roles`, `start`, `observe(state, role)`, `actions(state, role)`, `step(state, role, action_id)` and `outcome(state)`, plus an objective function. The SDK provides:
  - `Action` and `Population`;
  - `Jev(model=...)` and `Frontier(...)`;
  - `Session(env, population, judge, objective, policy, budget_ms)`, with `await observe(role, action_id)` and `await decide()`, which returns a decision with `action`, `values`, `uplift` and `belief`;
  - the policies `NoOffer`, `Rule(fn)`, `SingleStep()` and `Lookahead(depth)`;
  - `compare(...)` and `simulated_shoppers(...)`.

  The four choices:
  1. Async-first.
  2. The environment owns the site's legal moves, including prices.
  3. Value an unended session by asking Jev, in the same request, how likely each persona is to buy, with a developer override.
  4. Offline hidden shoppers are played by a frontier model through Bedrock, not by Jev.
- **Trim the frontier planner to Bedrock only?** It also supports Anthropic-direct and an OpenAI-style compatible gateway. Trimming fits "go lean" if Bedrock is the only one in use.

## Context

- Bryan's decisions not yet built in:
  - Break freely: *"it was a hackathon project and now we're working on it on our own so we should feel free to make the best design choices for what we're trying to build now."* The CLI, Python API and trace schema may all change.
  - Python, not Rust, for now. The engine's own work is 0.4–13 ms per round against 122–237 ms waiting on Jev, and Jev's 1,200 requests per minute caps throughput first. Revisit Rust only for one core shared by several languages, or for a hosted service at scale.
  - This pass demos the SDK plus simulated sessions and the viewer. The clickable storefront comes next pass.
  - No deadline: *"we're not in a hackathon anymore"*.
  - Wide and shallow by default, depth configurable: *"yes for now"*.
  - Push to `origin main` after each verified commit on this repo.
  - Bryan hasn't built an SDK before (*"you'll probably have to help me along"*), so explain public-surface choices as they're made.
- Keys:
  - Jev: `export TYPESAFE_API_KEY="$(security find-generic-password -s typesafe-api-key -w)"`.
  - Bedrock: Keychain `bedrock-token-acct-a` is short-term and often expired. The planner's default model `us.anthropic.claude-sonnet-4-6` has worked live.
- Traps:
  - Simulated shoppers lean toward buying, so simulated offer EVs are inflated. Trust their ranking before their size (evidence in `DESIGN.md`).
  - Offline evaluation where Jev plays both the hidden shopper and the swarm grades itself.
- Files:
  - `DESIGN.md`: rationale, prior art and evidence.
  - `README.md`: usage.
  - `jev_swarm/engine.py`: the runner to replace.
  - `jev_swarm/environment.py`: `GraphEnvironment`, to port.
  - `jev_swarm/policies.py`: the Jev client and batching.
  - `jev_swarm/transport.py`: HTTP.
  - `tests/test_framework.py`: the behavior guard.
