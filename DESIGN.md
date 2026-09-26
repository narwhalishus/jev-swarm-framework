# Design rationale

The reasoning behind this project: why it exists, what it assumes, and what it is trying to find out. The [README](README.md) covers how to use the code.

## Thesis

Jev turns a bounded semantic judgment (text in, a probability distribution over options you define out) into something cheap and fast enough to make many times over. This project explores what systems that unlocks. In particular it asks whether a swarm of such judgments exploring possible futures ("lookahead") beats one judgment at a time.

## Where Jev earns its place

A task fits when it has all four of these:

- **Messy semantic input.** The right response depends on meaning that is hard to enumerate as rules.
- **Bounded actions.** There is an explicit set of options, including doing nothing.
- **Many repeated decisions.** These can repeat across entities (many actors), across time (reconsidering as evidence arrives), across alternatives (comparing candidates or scenarios), or across uncertainty (act, inspect, wait, escalate).
- **Measurable consequences.** Outcomes can be observed and used to improve later decisions.

Speed has to buy something concrete. There are two ways it can:

- **A closing opportunity.** A better answer after the deadline is worthless. Think of a faster alternate route on the freeway: it is only useful before you pass the exit. Waiting is itself a decision, because it removes options.
- **A feedback loop.** Acting sooner produces evidence sooner. A fast, reasonable, reversible action followed by correction can beat a slower, better first guess (Boyd's law of iteration). This only works if the environment returns feedback. Re-asking a fast model about unchanged evidence buys nothing.

So the comparison with a frontier model is not "which makes the better single call". It is "which system reaches the better outcome before the opportunity closes, counting what it learns along the way".

If a rule can be written, write it. Rules are faster, cheaper, predictable and inspectable. Jev earns its place where **similar event sequences call for different responses because their semantic context differs**. The strong baseline is learned personalization (for example contextual bandits), not a handwritten script. What this project could add is richer semantic interpretation and useful lookahead. Adaptive personalization itself is not new.

## What the design assumes about Jev

These assumptions come from the API contract and TypeSafe's docs, which the README links. If Jev changes, revisit the design.

- **Stateless evaluation.** A request is one `state` plus independent typed questions (`choice`, `noul`, `score`). Memory, goals, beliefs and commitments live in the application. A swarm "instance" is a stored decision context evaluated by stateless calls, not a running process. What each actor knows matters at least as much as its persona.
- **Questions in one request don't see each other.** If question B needs A's answer, that takes another stage. Answers that are each plausible can still conflict, so constraints are reconciled in code.
- **Bounded output.** Jev selects and scores. It does not generate plans, dialogue or next world states. Candidates must be supplied (allow for "none fit"), and code or a simulator owns what an action does.
- **Text only.** Images and audio need a perception step first. That step can discard what the decision needs (a transcript loses tone of voice). It can also erase the cost advantage unless one perception pass feeds many decisions.
- **Documented weak spots.** The docs list literal reading, arithmetic and counting, date comparison, indirection, large irrelevant state, adversarial content, consistency across questions, and text generation. So math, dates, constraints and state transitions stay in code, state is filtered to what the question needs, and each question asks for one judgment.
- **Confidence is a statistic of the distribution's shape.** It is not an independent estimate of correctness. Whether the probabilities are calibrated for a given task has to be measured.
- **Cost and latency advantages are vendor claims.** Measure them on the actual workload.

## Using the distribution, not just its top option

A distribution supports more than picking the most likely option. It lets the system:

- keep alternatives alive until evidence separates them;
- spend more computation on ambiguous or consequential branches;
- try a less-preferred action to learn from its outcome;
- stress-test unlikely but costly possibilities;
- choose by consequences, because the best action is the one with the best expected outcome, not the one matching the most likely event.

Probability, desirability and information value are different quantities.

## Epistemic boundaries

These boundaries are why the traces, reports and prompts are careful about what they claim.

- A calibrated answer distribution is not a calibrated model of human behavior. "70% would cancel" does not mean 70% of matching customers cancel. Establishing that takes behavioral validation.
- Many personas running on one model are not independent evidence. They share the model's mistakes, and branch counts are not customer counts.
- Simulated branches explore the consequences of assumptions. They are not experiments. A thousand branches built on a wrong world model stay confidently wrong. Only real interactions test the assumptions.
- A projected action is never an observation.
- Per-step Jev outputs are not valid probabilities over whole paths. Combining them (for example summing log probabilities) ranks paths. It does not forecast them.
- More branches do not mean more knowledge. Expand a branch only if believing it could change what the system does.
- Customer observations, model judgments and hypothetical branches stay distinguishable in every artifact.

## Application: an adaptive storefront

The chosen application is **a storefront that responds to the customer's current obstacle while they are still deciding.**

**Predicting what a customer will do and deciding how to help are different problems.** The action is observed, but the motive is not. Say a customer removes the most expensive item from their cart. That could mean several things, each needing a different response:

- The total is over budget: show a cheaper alternative or an eligible incentive.
- They're choosing between similar items: show a concise comparison.
- Delivery is too slow: surface accurate delivery options.
- They're unsure about fit or compatibility: provide the missing information.
- They just don't want it: let them remove it without interruption.

Page views and dwell time are proxies for attention, not measurements of it. The semantic context tells these cases apart, and interpreting it is Jev's job. That context includes what the customer searched for, what they saw, and what changed before they hesitated. Removing a jacket after searching "under $100", after learning it isn't waterproof, or after seeing a late delivery estimate each calls for a different response. A discount helps only the first.

**The objective is incremental value, not conversion probability:**

```
value of intervening = E[contribution margin | intervene] − E[contribution margin | do nothing]
```

That quantity is causal and needs controlled experiments. An offer can be profitable in isolation and still lose money by discounting purchases that would have happened anyway.

| Component | Responsibility |
|---|---|
| Jev | Interpret context: likely friction, relevant assistance, whether interrupting is appropriate |
| Deterministic backend | Inventory, delivery facts, offer eligibility, margin floors, intervention frequency |
| Decision policy informed by experiments | Choose among eligible actions, including doing nothing; can start simple |

More principles for the storefront:

- **The "next best action" is rarely a popup.** It can reveal shipping costs, surface a comparison, answer a question, or make an alternative available. Sometimes helping means removing uncertainty, and sometimes it means leaving the customer alone.
- **No purchase is a legitimate success when nothing fits.** Otherwise the system drifts toward maximizing checkouts instead of purchases the customer stays happy with. Immediate sales, discount cost, returns and later satisfaction each measure something different.
- **There are two feedback timescales.** Within a session, the next click updates the interpretation. Across sessions, experiments show whether interventions help. A click on an offer is not evidence of incremental profit.
- **The time constraint is to respond while the relevant decision is still being made.** Check whether model latency is actually the bottleneck, because event detection and rendering count too. One good pattern: prepare eligible responses in the background as the session evolves, and recompute when meaningful evidence changes, not on every mouse movement. A deterministic trigger then displays a response that is already prepared. Speculate generously, but display with restraint.

## Swarm lookahead is a hypothesis to test

Three claims are kept separate:

1. Jev can interpret interaction context quickly enough to improve the interface.
2. Jev can predict useful near-term user actions.
3. Rolling those predictions forward picks better interventions than a single evaluation.

Claim 1 can hold even if claim 2 is weak. Claim 3 needs its own evidence.

**Different kinds of branch need different ingredients:**

| Branch type | What varies | What it gives you |
|---|---|---|
| Interpretation | Explanations of the current evidence | Decisions that hold up under ambiguity |
| Action | Actions the system or actor could take | Comparison of alternatives |
| World | How the environment responds | Contingency planning and stress tests |

Jev judges within a supplied situation. Something else has to say what happens next: transition rules, a simulator, a generative model, or a real action followed by observation.

**Branches work best as hypotheses about the customer.** The most useful branch is a hypothesis about the customer's goal or obstacle, with prepared responses attached. Each meaningful event runs the same loop:

1. Observe the event.
2. Update which hypotheses it supports or contradicts.
3. Add explanations the current set misses.
4. Merge equivalent hypotheses and prune weak ones. Being contradicted is different from being merely less likely, so keep a residual set.
5. Prepare eligible responses under the survivors.
6. Act or wait.

When the hypotheses **converge** on one response, act without first resolving the motive. For example, a cheaper alternative with a clear feature comparison helps whether the concern is price or suitability. When they **diverge** (say, a coupon versus sizing help), wait or offer a lightweight choice such as "Compare fit" or "See similar options".

**What the swarm is for, ranked by how much it depends on accurate human simulation:**

| Role | Dependence |
|---|---|
| Prepare likely next steps: comparisons, alternatives, eligible offers | Low: a wrong prediction mostly wastes computation |
| Test an intervention across plausible intentions | Moderate: coverage of plausible intentions matters |
| Forecast conversion under interventions | High: needs behavioral and causal validation |

Build around the first two.

**Mechanics lookahead needs before it can evaluate interventions:**

- **The website's action must appear in the simulated customer's next observation.** A separate "website" judge that just watches a predicted path and decides when to offer a coupon forecasts behavior. It does not evaluate what the intervention changes. Compare the options explicitly: no intervention, a comparison, an eligible offer.
- **Branching explodes.** Expanding the top 3 actions over five levels is already 363 nodes, and more once website responses branch too. So use a beam and a wall-clock budget, merge equivalent states, drop stale results, and expand only branches that could change the current decision.
- **Deeper is not more accurate.** Every hypothetical step compounds uncertainty and can amplify a wrong behavioral assumption.

**Lookahead plausibly earns its place when the best action now depends on what happens next.** Take a customer who compares jackets, checks delivery, and removes one. A single-step decision might recommend an item. Lookahead can discover that one low-friction question ("What matters most: price, weather protection, or delivery date?") unlocks a well-tailored next response for each answer. If every decision collapses to "which coupon, right now?", lookahead adds little.

**The test is to run the same scenarios three ways:** handwritten rules, single-step Jev, and branching Jev. If single-step matches branching, the product still stands and the swarm is optional. The first experiment is single-step against two-step lookahead with a small branch budget, on a scenario where asking or preparing something now improves the next interaction. Lookahead has shown its value if it changes the decision for a clear reason. Drawing a bigger tree does not count.

Lookahead is easier to validate where transitions are known and goals are explicit, as in games or constrained workflows. In a storefront the hard part is the human. So the defensible claim is: *the storefront explores possible customer needs and prepares helpful next steps, updating as the customer acts.* It is not "we simulate customers to maximize conversion".

## Directions considered

- **Semantic load testing.** Synthetic users with goals react to what a product actually says and does. Change the cancellation copy or inject an error, then watch retries, abandonment and escalation. The defensible framing is "where does this experience break under varied goals and interpretations?", never "we predict your conversion rate".
- **Living-world sandbox, agent flight recorder, incident-response simulator.** These also fit the criteria. The storefront was chosen over them.
- **Predictive tool palette for an editor like Photoshop.** Dropped in favor of the storefront. It has cleaner feedback (the next tool chosen, undo) but a weaker business case. Automatic tool switching carries a high error cost, because the user's next gesture could do something unexpected. Understanding image content would also need a perception layer.
