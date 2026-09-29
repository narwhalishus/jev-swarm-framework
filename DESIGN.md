# Design rationale

The reasoning behind this project: why it exists, what it assumes, and what it is trying to find out. The [README](README.md) covers how to use the code.

## Thesis

Jev turns a bounded semantic judgment (text in, a probability distribution over options you define out) into something cheap and fast enough to make many times over. This project explores what systems that unlocks. In particular it asks whether a swarm of such judgments exploring possible futures ("lookahead") beats one judgment at a time.

## What this project is

A framework and SDK, not an application. It runs one kind of experiment: a swarm of Jev judgments exploring possible futures from a starting state. The only difference between its uses is where that starting state comes from.

- **Offline.** The starting state is synthetic. Actors with explicit goals move through a controlled environment, and their paths are compared across conditions. No real events arrive.
- **Live.** The starting state is a real user's current state, and the experiment keeps changing as they act. Each real action prunes the branches it contradicts and keeps the ones it confirms. New branches are seeded from the user's latest decisions. This is how an interface reacts to user decisions and actions, and the storefront below is the motivating example.

An offline run is a live run that never receives an event. The core operation is the same for both: restart from an observed state, keep whatever still fits, and search further within a budget.

It is an SDK in the strict sense: the host application calls it. A framework calls your code, and the offline runner has that shape. Real-time use needs the other shape, because the host app owns the event loop. Clicks arrive from the UI, so the app calls something like `session.observe(event)` and `session.best_action()`. An offline experiment is then the same SDK fed by simulated events.

The building blocks stay domain-free. Storefront logic lives in environments, policies and applications, never in the engine.

| Building block | What it is | Storefront example |
|---|---|---|
| Judgment | Jev: repeated, stateless, bounded judgments over state the application holds | Which action a persona takes next; which offer form fits |
| Environment | State, legal actions and transitions, all owned by code | Cart, product pages, checkout |
| Roles and policies | Who acts, in what order. Each role's policy is swappable: rules, single-step Jev, or lookahead | The customer (played by Jev in simulation) and the site, which intervenes |
| Population | Weighted guesses about who the real subject is | Shopper personas |
| Objective | The domain's value function, owned by code | Margin plus the value of clearing inventory, within the ZOPA |
| Session | The live loop: observe a real event, reweight and prune guesses, spawn new ones, search under a budget, return the best action | One shopping session |
| Orchestrator | A frontier model that generates what Jev cannot and oversees runs, off the per-decision hot path | Writes personas and proposes new guesses |
| Trace and oversight UI | A record of every observation, judgment and branch, plus a read-only view of it | Persona weights, EV per offer, uplift labels |

Two blocks carry extra rules:

- **The orchestrator's interventions are bounded and logged.** An orchestrator steering a swarm can quietly bias it toward its own hypothesis. So every intervention is logged with a reason, and it cannot change legal actions, goals or transitions.
- **The oversight UI surfaces what matters for judging a run.** That means why each branch lives or dies, where branches converge or diverge, and how differently actors behave at the same state. It reads traces and never changes a run.

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
- Simulated branches explore the consequences of assumptions. They don't test those assumptions. A thousand branches built on a wrong world model stay confidently wrong. Only real interactions test the assumptions, which is what live experiments add.
- Persona variance is not behavioral variance. Frontier-written personas lean toward interesting diversity rather than realistic diversity. Every actor is also judged by the same Jev weights, so distinct personas can collapse into similar behavior. Measure behavioral spread: at the same state, do different actors produce different action distributions? Pairwise Jensen–Shannon divergence between those distributions is one measure.
- Simulated shoppers lean toward buying. In published evaluations, LLMs rarely predicted a real shopper quitting, and simulated A/B effects ran 10–30× larger than the real ones even when the direction matched. So offer EVs from simulation are inflated. Trust their ranking and direction before their magnitude.
- A projected action is never an observation.
- Per-step Jev outputs are not valid probabilities over whole paths. Combining them (for example summing log probabilities) ranks paths. It does not forecast them.
- More branches do not mean more knowledge. Expand a branch only if believing it could change what the system does.
- Customer observations, model judgments and hypothetical branches stay distinguishable in every artifact.

## Motivating application: an adaptive storefront

The application the framework should make buildable is **a storefront that responds to the customer's current obstacle while they are still deciding.**

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
| Forecast outcomes under interventions | High: needs behavioral and causal validation |

The first two roles are safe to build on now. The third is the incentive use case (see "Dynamic incentives" below). There the swarm ranks offers by simulated EV, and a real holdout decides how far to trust it.

**Mechanics lookahead needs before it can evaluate interventions:**

- **The website's action must appear in the simulated customer's next observation.** A separate "website" judge that just watches a predicted path and decides when to offer a coupon forecasts behavior. It does not evaluate what the intervention changes. Compare the options explicitly: no intervention, a comparison, an eligible offer.
- **Branching explodes.** Expanding the top 3 actions over five levels is already 363 nodes, and more once website responses branch too. So use a beam and a wall-clock budget, merge equivalent states, drop stale results, and expand only branches that could change the current decision.
- **Deeper is not more accurate.** Every hypothetical step compounds uncertainty and can amplify a wrong behavioral assumption.
- **Breadth is cheap, and depth is not.** Independent questions in one request cost little extra time; TypeSafe's own "speculative fan-out" pattern packs every question you might need into one request and discards the irrelevant answers. Each level of depth is another sequential round trip.

**Lookahead plausibly earns its place when the best action now depends on what happens next.** Take a customer who compares jackets, checks delivery, and removes one. A single-step decision might recommend an item. Lookahead can discover that one low-friction question ("What matters most: price, weather protection, or delivery date?") unlocks a well-tailored next response for each answer. If every decision collapses to "which coupon, right now?", lookahead adds little.

**The test is to run the same scenarios three ways:** handwritten rules, single-step Jev, and branching Jev. If single-step matches branching, the product still stands and the swarm is optional. The first experiment is single-step against two-step lookahead with a small branch budget, on a scenario where asking or preparing something now improves the next interaction. Lookahead has shown its value if it changes the decision for a clear reason. Drawing a bigger tree does not count.

Lookahead is easier to validate where transitions are known and goals are explicit, as in games or constrained workflows. In a storefront the hard part is the human. So the defensible claim is: *the storefront explores possible customer needs and prepares helpful next steps, updating as the customer acts.* It is not "we simulate customers to maximize conversion".

## Live experiments build on established patterns

The loop above (observe, prune, spawn, prepare) is a well-studied pattern. The closest algorithm is POMCP: an online planner that keeps a set of sampled guesses about a hidden state, searches from them, and re-roots at each real observation. The closest application is POMDP dialogue systems, which track a hidden user goal and choose system actions in real time. One lesson from that work: dialogue policies trained entirely on a simulator did worse with real users than partly simulator-trained ones, apparently because they exploited simulator quirks. Three ideas map onto the loop:

- **Receding-horizon planning (model predictive control).** Plan a few steps ahead, act, observe, then plan again from the new state.
- **Particle filtering.** Personas are guesses about who the user is and what they want. Each real action strengthens the guesses that predicted it and weakens the rest. Weak guesses are dropped, and new ones are proposed when none of the survivors explain the user.
- **Search-tree reuse.** POMCP keeps the subtree under the real move and discards the rest. DESPOT instead builds a fresh tree at each decision.

**How the belief updates.** On each real action `a`, each persona's weight is multiplied by the probability that persona gave `a`, accumulated in log space: `w_i ← w_i × P(a | history, persona_i)`. The weights rank guesses; they are not calibrated likelihoods until live data measures them. Only real events update the belief, never imagined ones.

**Two diagnostics catch two different failures:**

- **Collapse.** The effective sample size, `ESS = 1 / Σ w_i²`, falls when the weights pile onto a few personas. The remedy is resampling that keeps diversity.
- **Nobody explains the user.** The swarm's mixture gives the real action low probability, even while ESS looks healthy. That points to a missing hypothesis or a wrong behavioral model, and it is the orchestrator's trigger to propose new personas.

**New personas are proposals, not samples.** Before a frontier-proposed persona gets a weight, it is scored against the user's real history so far: Jev says how likely that persona was to take each observed action, in one batched request.

**The belief persists, and the tree need not.** At Jev's speed rebuilding the tree on each event is affordable, so reuse is an optimization. The engine answers on demand: when the user acts, it returns the best action from whatever search has finished.

**A live experiment checks itself.** Every real action scores the prediction made just before it. Score the mixture's prediction, `p(a) = Σ w_i p_i(a)`, with log loss and calibration against four baselines: Jev with no persona, a single persona, shuffled personas, and empirical action frequencies. If personas don't beat no-persona Jev, the population isn't earning its cost. Offline runs cannot produce this measurement, and it is the direct test of claim 2 above.

## Dynamic incentives: finding the ZOPA

The live experiment feeds a policy that adjusts incentives for each user. The goal is an honest deal both sides prefer. The zone of possible agreement (ZOPA) lies between the store's floor and the customer's ceiling. The store knows its floor exactly: unit cost, margin target, and the value of clearing inventory. The customer's ceiling is the unknown, and the swarm's reading of the session is the evidence about it. When no price clears both, there is no deal to find, and the right move is no offer. The storefront's objective (incremental value) and its division of responsibilities still apply.

The decision splits three ways:

- **Jev decides when**, by reading whether the customer is still open or already settling.
- **Jev decides which form fits**: a bundle price, buy-2-get-1, free shipping, or a later text or email.
- **The backend decides how much**, by pricing each form against the floor.

**Worked example: three dresses.** A shopper has three $100 dresses in the cart. They want all three, but $300 is too much. The window is while they still want all three. Once they settle on one, an incentive has to reverse a decision instead of tipping an open one. The form of the offer matters economically, not just psychologically. With an illustrative unit cost of $40, against a baseline where they buy one dress (margin $60):

| Offer | Store margin | Versus buying one |
|---|---|---|
| All 3 for $240 | $120 | +$60 |
| 2 for $170 | $90 | +$30 |
| Buy 2 get 1 (3 for $200) | $80 | +$20 |
| All 3 for $240, to a shopper who would have paid $300 | $120 instead of $180 | −$60 |

Offers tied to buying more only cost money when they produce the extra sale. Their one real risk is the last row: the customer who would have bought all three anyway. Pricing by quantity ("2 for $X, 3 for $Y") comes close to the profit of full bundle pricing. Keeping single items on sale at their normal price lets customers pick the deal that suits them.

**The swarm prices that false positive.** Uplift modeling sorts customers by what an offer changes:

- **Persuadables** buy only if offered.
- **Sure things** buy either way. They are the false positive above.
- **Lost causes** buy neither way.
- **Sleeping dogs** are put off by the offer.

No single judgment reliably tells a sure thing from a persuadable. The swarm can do it probabilistically. For each surviving persona and each eligible offer, including none, it simulates the reaction, labels the persona by uplift type, and computes:

```
EV(offer) = Σ over personas: weight × [store value if offered − store value if not offered]
```

Sure things count against every offer, so the false positive is priced in. If no offer beats doing nothing, the swarm offers nothing. This is also the sharpest form of the single-step against lookahead test: single-step asks the mindset question directly, and lookahead simulates both outcomes.

**There are two layers of experiment.** Within a session, the experiments are simulated. The real customer produces one outcome, and what they would have done otherwise is never observed.

- **Per session**, the swarm picks the offer by simulated EV.
- **Across sessions**, a persistent no-offer holdout measures whether those EVs match reality. The decision log records the eligible offers, the chosen one and the probability of choosing it, the policy version and the outcome. Later causal evaluation needs all of it, and none of it can be backfilled.

**Guardrails:**

- **The swarm proposes, and real outcomes decide.** The swarm is good at telling which incentive is relevant: budget, delivery, or none at all. Whether an incentive pays is a causal question. It has to be learned from real outcomes, with a control group that gets no incentive, as a contextual bandit would learn it. Tuning incentives against simulated acceptance only optimizes the simulation's assumptions.
- **Happiness needs a measured stand-in before anything optimizes it.** Returns, repeat purchases or complaints can serve. Without one, the optimizer quietly trades happiness away for margin.
- **Incentives tied to behavior train that behavior.** If hesitating reliably produces a coupon, customers learn to hesitate. A randomized experiment on Alibaba covering over 100 million customers found that cart promotions changed later behavior: more items added to carts and lower prices paid. Frequency caps and some unpredictability belong in the deterministic backend.
- **Personalized offers carry disclosure duties.** New York requires the notice "THIS PRICE WAS SET BY AN ALGORITHM USING YOUR PERSONAL DATA" next to a personalized price. The EU requires telling customers when a price was personalized by automated decision-making. Regulators also act against fake urgency. Eligibility and disclosure rules live in the backend. Check the rules in force before real customers see offers.

## Prior art and evidence

**Planning under a hidden user type**

- Silver & Veness, [Monte-Carlo Planning in Large POMDPs](https://davidstarsilver.wordpress.com/wp-content/uploads/2025/04/monte-carlo-planning-in-large-pomdps.pdf) (POMCP). Keeps a particle belief, searches from sampled states, and reuses the subtree after the real move.
- Ye et al., [DESPOT: Online POMDP Planning with Regularization](https://jair.org/index.php/jair/article/download/11043/26215). Builds a fresh tree per decision, stops anytime using value bounds, and regularizes against overfitting its sampled scenarios.
- Doucet & Johansen, [A Tutorial on Particle Filtering and Smoothing: Fifteen Years Later](https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF2011.pdf). Covers weight degeneracy, ESS and rejuvenation. A healthy ESS does not prove the particles cover the right region.
- Young et al., [POMDP-based statistical spoken dialogue systems: a review](https://www.microsoft.com/en-us/research/publication/pomdp-based-statistical-spoken-dialogue-systems-a-review/), and Gašić & Young on dialogue manager optimisation. Track a hidden user goal; a fully simulator-trained policy did worse with humans than a partly trained one.
- Zhao, Lee & Hsu, [LLM-MCTS](https://arxiv.org/abs/2305.14078). The LLM supplies beliefs and search heuristics while transitions stay known and deterministic.

**Incentives and causal evaluation**

- Radcliffe & Surry, [uplift modeling](https://stochasticsolutions.com/pdf/sig-based-up-trees.pdf), the source of the four uplift types. Gutierrez & Gérardy, [Causal Inference and Uplift Modelling: A Review](https://proceedings.mlr.press/v67/gutierrez17a.html).
- Dudík et al., [Doubly Robust Policy Evaluation and Optimization](https://doi.org/10.1214/14-STS500). Explains why the decision log records action probabilities.
- The Alibaba cart-promotion experiment, [long-term and spillover effects of price promotions](https://profiles.wustl.edu/en/publications/the-long-term-and-spillover-effects-of-price-promotions-on-retail/). Evidence that customers respond strategically.
- Chu, Leslie & Sorensen, [Bundle-Size Pricing as an Approximation to Mixed Bundling](https://www.aeaweb.org/articles?id=10.1257/aer.101.1.263), building on Adams & Yellen's mixed bundling.
- Bergemann, Koh & Morris, *Mechanism Design for Alignment and Control*. Mechanism design with agents whose preferences and capabilities are private. Background for incentive design, and for overseeing agents.

**Simulated users**

- [OPeRA](https://aclanthology.org/2026.acl-long.2033/). On real Amazon sessions, the best model predicted the exact next action 21.5% of the time with a persona and 22.1% without. Personas helped predict the type of action but not the exact action, and models rarely predicted a shopper quitting.
- [ShopCART](https://aclanthology.org/2026.acl-long.2034/). Exact next-action accuracy was 11.9% for prompting alone and 17.3% after training on behavior.
- [PAARS](https://aclanthology.org/2025.realm-1.11/). Personas mined from shopping histories raised four-way purchase prediction from 41% (history only) to 47%. The direction of simulated A/B effects matched reality in 2 of 3 tests, but their size ran 10–30× larger; the authors suspect a bias toward purchasing.
- [AgentA/B](https://arxiv.org/abs/2504.09723). Directional agreement with a large Amazon experiment, but agents took far fewer actions than humans.
- Argyle et al., [Out of One, Many](https://doi.org/10.1017/pan.2023.2), for persona-conditioned sampling. The critiques: Bisbee et al., [reduced variance and unstable estimates](https://doi.org/10.1017/pan.2024.5); Wang et al., [flattening of identity groups](https://doi.org/10.1038/s42256-025-00986-z); Aher et al., [hyper-accuracy distortion](https://arxiv.org/abs/2208.10264).
- Hewitt, Ashokkumar et al. in [Nature](https://doi.org/10.1038/s41586-026-10742-x). LLM predictions of survey-experiment effects correlated strongly with the real ones but overestimated their size.
- [RecSim](https://arxiv.org/abs/1909.04847), a configurable test lab rather than a validated population. [Virtual-Taobao](https://arxiv.org/abs/1805.10000), a simulator grounded in large randomized logs and validated by transferring policies online.

**Platform and regulation**

- TypeSafe, [speculative fan-out](https://docs.typesafe.ai/patterns/fan-out).
- The FTC's [surveillance pricing study](https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-surveillance-pricing-study-indicates-wide-range-personal-data-used-set-individualized-consumer); the EU [Omnibus Directive](https://eur-lex.europa.eu/eli/dir/2019/2161/oj) on disclosing personalized prices; New York's [Algorithmic Pricing Disclosure Act](https://ag.ny.gov/press-release/2025/attorney-general-james-warns-new-yorkers-about-algorithmic-pricing-new-law-takes).

## Directions considered

- **Semantic load testing.** Synthetic users with goals react to what a product actually says and does. Change the cancellation copy or inject an error, then watch retries, abandonment and escalation. The defensible framing is "where does this experience break under varied goals and interpretations?", never "we predict your conversion rate".
- **Living-world sandbox, agent flight recorder, incident-response simulator.** These also fit the criteria. The storefront was chosen over them.
- **Predictive tool palette for an editor like Photoshop.** Dropped in favor of the storefront. It has cleaner feedback (the next tool chosen, undo) but a weaker business case. Automatic tool switching carries a high error cost, because the user's next gesture could do something unexpected. Understanding image content would also need a perception layer.
