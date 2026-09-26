# Jev Swarm Framework

A headless Python framework for controlled experiments with diverse synthetic actors.

A frontier model defines the experiment and actor profiles. Jev evaluates each actor's next action from an explicit legal action set. A deterministic environment applies the action, appends the resulting observation to that actor's history, and advances the simulation. Runs stop at a terminal state, depth limit, deadline, or resource budget.

**Python 3.11+. Zero mandatory third-party dependencies. No website, browser service, or database required.**

For why it is built this way and what it is trying to find out, see [DESIGN.md](DESIGN.md).

## Run it now

From this directory:

```bash
python -m jev_swarm run \
  --environment examples/storefront.json \
  --actors 8 --depth 6 --mode lookahead \
  --branch-factor 3 --beam-width 3 \
  --policy demo --out runs/first-demo
```

This is an **offline seeded heuristic**, not Jev. It verifies the simulation machinery without credentials. The console, traces, and reports label the policy. It does not interpret the experiment's text. There is no silent fallback from a failed live API call to demo mode.

For one sampled journey per actor:

```bash
python -m jev_swarm run --environment examples/onboarding.json \
  --actors 12 --depth 7 --mode sample --policy demo
```

## Live Jev decisions

Set `TYPESAFE_API_KEY` in your shell or secret manager. The program reads environment variables and does not save API keys in traces. `.env.example` lists supported variables; the framework does **not** auto-load `.env` files.

```bash
python -m jev_swarm run \
  --environment examples/storefront.json \
  --actors 8 --depth 6 --mode lookahead \
  --branch-factor 3 --beam-width 3 \
  --policy jev --jev-model jev-latest \
  --batch-size 16 --concurrency 4 \
  --out runs/live-jev
```

This uses editable, deterministically diversified profile templates and **live Jev**. It does not require a frontier key. Pin a supported Jev version for comparisons; `jev-latest` may change.

## Full pipeline: Bedrock → N actors → Jev → oversight

Set `TYPESAFE_API_KEY`. On macOS the Bedrock adapter reads only the Keychain service
`bedrock-token-acct-a`; it does not enumerate other credentials. On other machines,
set `AWS_BEARER_TOKEN_BEDROCK`. Tokens are never written into traces.

```bash
python -m jev_swarm run \
  --environment examples/storefront.json \
  --objective 'Explore how delivery deadlines, budget limits and product suitability change shopping journeys.' \
  --actors 8 --seed 42 --planner bedrock \
  --bedrock-keychain bedrock-token-acct-a \
  --aws-region us-east-1 \
  --frontier-model us.anthropic.claude-sonnet-4-6 \
  --policy jev --mode lookahead --depth 6 \
  --branch-factor 3 --beam-width 3 --timeout 300 \
  --supervise-every 2 --review --out runs/bedrock-swarm
```

Choose a region and model your Bedrock account can invoke. This uses the Bedrock
Runtime Converse API with bearer-token authentication and structured tool outputs.

The planner creates a shared instruction, N distinct profiles and a hypothesis.
Every two rounds, the optional supervisor can continue, stop, or prune named
active branches, with its reason saved in the trace. It cannot change legal
actions, actor goals, or environment transitions. Oversight adds frontier latency
between batches. `--review` writes a final narrative review.

Profile variation is decision-relevant; actors are not merely assigned different
names. The seed is logged, but model outputs are not guaranteed deterministic.
Save the plan and pin model IDs for comparisons.

For Anthropic directly, use `--planner anthropic`, `ANTHROPIC_API_KEY`, and an
explicit `--frontier-model` available to your account.

## Visual oversight

Open `examples/live-onboarding/viewer.html` for a self-contained visualization
of an actual Jev lookahead run. Every run exports its own `viewer.html`.
Click actors and nodes to inspect their goals, observations, history,
action distributions and branch status. Round timings and supervisor decisions
appear below the tree. No JavaScript dependencies or external services required.

To watch a run as checkpoints arrive, use a second terminal:

```bash
python -m jev_swarm watch runs/bedrock-swarm
```

Open http://127.0.0.1:8765. The view refreshes every 1.5 seconds and is read-only.
The server binds only to localhost. You can start it before the run directory
exists, or import another `run.json` in the viewer.

### Other frontier gateways

Use `--planner compatible`, set `FRONTIER_API_KEY`, `FRONTIER_MODEL`, and `FRONTIER_BASE_URL` (an HTTPS root ending in `/v1`). This adapter calls `/chat/completions` with `response_format: {"type":"json_object"}`. The gateway must support that contract. API errors are explicit.

## Save and edit a plan before running

```bash
python -m jev_swarm plan \
  --environment examples/onboarding.json \
  --objective 'Explore why evaluators do not finish a first task.' \
  --actors 6 --seed 17 --planner seeded --out experiment.json

# Edit goals, traits and base_prompt in experiment.json.
python -m jev_swarm run --environment examples/onboarding.json \
  --experiment experiment.json --policy jev --depth 8 --out runs/edited-plan
```

`plan --planner bedrock --frontier-model ...` generates a live frontier plan instead. Loading `--experiment` preserves its actors and seed; CLI `--actors`, `--objective`, `--seed`, and planning options are not applied to the saved plan. Planner options still select the provider for supervision or review.

## Two execution modes

### Sampled rollouts (`--mode sample`)

Each actor samples one legal action from the returned distribution at each round. It retains its own evolving history. Sampling uses a stable actor/path seed. Every actor has at most one final path. The actor policy sees only its own observation and history, not other actors or the future state graph.

### Bounded lookahead (`--mode lookahead`)

Each active path expands its top K nonzero actions, then retains at most B active paths **per actor per depth**. Terminal and depth-limited paths are recorded but never expanded. Lower-scoring active branches are marked `pruned` and remain inspectable.

- `--branch-factor K`: maximum children per evaluated node.
- `--beam-width B`: maximum retained nonterminal paths per actor.
- `--depth D`: maximum actions along any path.
- `--max-decisions`: maximum evaluated nodes; checked before a round.
- `--max-nodes`: maximum stored nodes; checked conservatively before a round.
- `--timeout`: overall run deadline in seconds.

Path ranking sums log action probabilities. This is a **search heuristic, not a calibrated probability of an actual human journey**. Top-K expansion can omit important unlikely paths, and terminal branch counts are not independent customers. This prototype does not merge paths: histories can differ even when current screens match.

The first frontier contains N nodes. Later active frontiers are bounded by N × B. A round batches independent Jev questions, with bounded concurrent requests and a conservative byte budget. Sequential depths still require sequential rounds: parallelism does not make D-step lookahead a single inference.

## Use any controlled environment

The engine imports no storefront logic. Implement this async protocol:

```python
class Environment:
    def describe(self) -> dict: ...
    async def reset(self, actor, seed) -> dict: ...
    async def observe(self, state, actor) -> dict: ...
    async def available_actions(self, state, actor) -> list[Action]: ...
    async def step(self, state, action_id, actor) -> dict: ...
    async def terminal(self, state, actor) -> str | None: ...
```

State must be JSON serializable. `step` returns a new independent snapshot. Return `None` from `terminal` to continue, or an outcome label such as `success`, `exit`, or `completed_with_help`. All action IDs must be unique within a state. A nonterminal state needs at least one action.

For branching, transitions must be deterministic from the supplied state, or capture RNG state explicitly in the snapshot. Do not store branch-specific mutable state in a shared adapter. The engine copies snapshots before calling an adapter, but cannot isolate side effects hidden inside your implementation.

`describe()` records adapter version/configuration in the trace. `observe()` controls what the actor knows; keep hidden state and future screens out of it. The engine does not ask Jev to invent future observations.

A complete Python adapter is included:

```bash
python -m examples.custom_adapter
```

It simulates setting up a project and adding a first task, without a graph file.

### Declarative graph adapter

For prototypes, provide JSON with `initial_state` and `states`. Every state has an observation and either actions or an outcome. An action's `to` destination and optional `set` update are applied by code. Destinations are not sent to the actor model.

See `examples/storefront.json` and `examples/onboarding.json`. The storefront's shipping offer is a **fixed experimental condition**, not an incentive autonomously optimized by the framework. Optional `actor_profiles` define relevant offline profile templates; they are not observed customer data.

### Browserbase and external tools

A browser adapter (for example on Browserbase) would need to map observed UI elements to stable action IDs and return textual observations. Lookahead additionally needs a separate isolated browser/environment snapshot per branch, or reliable replay into cloned sessions. One shared live tab cannot safely represent multiple futures. Use a controlled test environment; predicted branches must not create real purchases or send messages.

Images and audio would require a perception adapter that converts them to appropriate textual observations before Jev evaluation.

## Python API

```python
import asyncio, json
from jev_swarm import GraphEnvironment, JevPolicy, RunConfig, SwarmRunner, seeded_experiment

async def main():
    env = GraphEnvironment(json.load(open('examples/onboarding.json')))
    experiment = seeded_experiment('Explore setup friction', 8, 42, env.describe())
    runner = SwarmRunner(env, JevPolicy(),
        on_event=lambda kind, payload: print(kind, payload) if kind == 'round' else None)
    result = await runner.run(experiment,
        RunConfig(depth=6, mode='lookahead', branch_factor=3, beam_width=3))
    print(result.summary())

asyncio.run(main())
```

`on_event` is a synchronous progress/logging hook. `checkpoint` receives the result after each committed round. These hooks should be quick and should not mutate the result. Pass `supervisor=planner.supervise` to `SwarmRunner` and set `RunConfig(supervise_every=2)` for periodic frontier oversight.

## Artifacts and recovery

Each run writes:

| File | Contents |
|---|---|
| `experiment.json` | Shared prompt, profiles, seed, planner provenance |
| `run.json` | Complete state snapshots, histories, distributions, confidence, pruning, limits and model provenance |
| `events.jsonl` | Streaming decisions, transitions and round summaries |
| `summary.json` | Synthetic path counts, resource usage and run status |
| `report.md` | Readable summary and actor paths |
| `viewer.html` | Self-contained interactive actor/tree/telemetry explorer |
| `tree.dot` | Graphviz visualization source for the branching DAG |
| `frontier-review.md` | Optional model review |

`run.json` is atomically checkpointed after complete rounds. Invalid/incomplete model responses fail the run; they do not produce fabricated decisions. A failed round is not committed. Jev calls retry transient errors with bounded backoff; reports count logical batch requests, not retry attempts. Summed batch latency is not per-actor latency. The CLI exits nonzero on a deadline, resource limit, interruption, or error. Cancellation stops scheduling and discards uncommitted results; an in-flight standard-library HTTP request may continue until its per-request timeout.

```bash
python -m jev_swarm report runs/first-demo/run.json
python -m jev_swarm run --resume runs/live-jev/run.json --out runs/resumed
```

CLI resume restores graph configuration, experiment, seed and run budgets, and uses the original provider/model alias. It resumes pending active nodes; the deadline restarts for the new invocation. Already completed runs are returned unchanged. For a checkpoint with supervision enabled, also pass `--planner bedrock` (and your region/model options) when resuming. Exhausted node/decision budgets require a new experiment with larger limits. Resume does not preserve the previous process's HTTP requests or guarantee unchanged responses from a moving model alias. Custom adapters can resume via the Python API by supplying the same adapter/configuration.

An output directory containing `run.json` is protected against accidental overwrite unless `--overwrite` is supplied.

## What a run does and doesn't establish

A run does not establish that Jev's action distributions model humans accurately, that a larger swarm provides independent evidence, or that a simulated intervention produces real conversion lift. A synthetic A/B comparison is a scenario experiment, not a randomized experiment with real users. Keep customer observations, model judgments and hypothetical branches distinguishable. [DESIGN.md](DESIGN.md) explains why.

`examples/live-*` hold traces from real Jev runs. Each trace records its policy and model. Round timings include network and provider time from wherever the run executed, so they are not interaction-latency measurements.

## Verification

```bash
python -m unittest discover -s tests -v
```

No API key is required.

Optional installation provides the `jev-swarm` executable:

```bash
python -m pip install -e .
```

You can always run directly from source with `python -m jev_swarm`, without installing anything.

## API references

- Jev API: https://docs.typesafe.ai/api
- Jev state and question isolation: https://docs.typesafe.ai/concepts/state
- Jev limits: https://docs.typesafe.ai/models
- Jev limitations: https://docs.typesafe.ai/model-jaggedness/jev-1.13
- Bedrock bearer tokens and Converse: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
- Anthropic models and account-specific IDs: https://platform.claude.com/docs/en/models/overview
