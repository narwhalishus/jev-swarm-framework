"""Bounded sampled rollouts and breadth-first beam lookahead."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import math
import random
import time
from typing import Awaitable, Callable
from .environment import Environment
from .models import DecisionContext, Experiment, JSON, Node, RunConfig, RunResult
from .policies import DecisionPolicy, stable_seed

EventCallback = Callable[[str, JSON], None]
CheckpointCallback = Callable[[RunResult], None]

class SwarmRunner:
    def __init__(self, environment: Environment, policy: DecisionPolicy, *,
                 on_event: EventCallback | None = None, checkpoint: CheckpointCallback | None = None,
                 supervisor: Callable[[RunResult], Awaitable[JSON]] | None = None):
        self.environment, self.policy = environment, policy
        self.on_event, self.checkpoint = on_event, checkpoint
        self.supervisor = supervisor

    def emit(self, kind: str, payload: JSON) -> None:
        if self.on_event:
            self.on_event(kind, payload)

    async def run(self, experiment: Experiment, config: RunConfig | None = None, *,
                  resume: RunResult | None = None) -> RunResult:
        config = config or RunConfig()
        config.validate()
        experiment.validate()
        if config.supervise_every and not self.supervisor:
            raise ValueError("supervise_every requires a supervisor callback")
        if config.max_nodes < len(experiment.actors):
            raise ValueError("max_nodes must accommodate all initial actors")
        if resume:
            if resume.environment != self.environment.describe():
                raise ValueError("Checkpoint environment differs from the current adapter")
            if resume.policy != self.policy.name:
                raise ValueError("Resume must use the same policy and model alias")
            if resume.experiment != experiment or resume.config != config:
                raise ValueError("Resume must use the checkpoint experiment and configuration")
            result = deepcopy(resume)
            if result.status == "completed":
                return result
            result.status, result.error = "running", None
        else:
            result = RunResult(experiment, config, self.environment.describe(),
                               created_at=datetime.now(timezone.utc).isoformat(), policy=self.policy.name)
        actors = {a.id: a for a in experiment.actors}
        try:
            async with asyncio.timeout(config.timeout_seconds):
                if not result.nodes:
                    roots = []
                    for actor in experiment.actors:
                        state = await self.environment.reset(actor, stable_seed(experiment.seed, actor.id))
                        outcome = await self.environment.terminal(deepcopy(state), actor)
                        roots.append(Node(f"{actor.id}/root", actor.id, deepcopy(state),
                                          status="terminal" if outcome else "active", outcome=outcome))
                    result.nodes = roots
                    self.emit("started", {"actors": len(actors), "policy": self.policy.name, "mode": config.mode})
                    if self.checkpoint:
                        self.checkpoint(result)
                while True:
                    frontier = [n for n in result.nodes if n.status == "active"]
                    if not frontier:
                        result.status = "completed"
                        break
                    # Retry a pending oversight checkpoint before advancing a resumed run.
                    if (config.supervise_every and result.rounds
                            and len(result.rounds) % config.supervise_every == 0
                            and not any(check["round"] == len(result.rounds) for check in result.supervision)):
                        assert self.supervisor is not None
                        began = time.perf_counter()
                        oversight = await self.supervisor(deepcopy(result))
                        if not isinstance(oversight, dict):
                            raise ValueError("Supervisor must return an oversight object")
                        active_ids = {n.id for n in result.nodes if n.status == "active"}
                        prune_ids = oversight.get("prune_node_ids", [])
                        if oversight.get("action") not in {"continue", "stop"} or not isinstance(prune_ids, list) or any(not isinstance(x, str) for x in prune_ids) or not set(prune_ids).issubset(active_ids):
                            raise ValueError("Invalid supervisor decision; completed simulation rounds are preserved")
                        if not isinstance(oversight.get("reason"), str):
                            raise ValueError("Supervisor decision requires a reason")
                        oversight = {**oversight, "round": len(result.rounds), "duration_ms": round((time.perf_counter()-began)*1000,3)}
                        result.supervision.append(oversight)
                        for node in result.nodes:
                            if node.id in prune_ids:
                                node.status = "supervisor_pruned"
                        if oversight["action"] == "stop":
                            result.status = "supervisor_stopped"
                        if self.checkpoint:
                            self.checkpoint(result)
                        self.emit("supervision", oversight)
                        if oversight["action"] == "stop":
                            break
                        continue
                    for n in frontier:
                        if n.depth >= config.depth:
                            n.status = "depth_limit"
                    frontier = [n for n in frontier if n.status == "active"]
                    if not frontier:
                        result.status = "completed"
                        break
                    decisions_used = sum(r["decisions"] for r in result.rounds)
                    if decisions_used + len(frontier) > config.max_decisions:
                        result.status = "decision_budget"
                        break
                    started = time.perf_counter()
                    contexts = []
                    for node in frontier:
                        actor = actors[node.actor_id]
                        observation = await self.environment.observe(deepcopy(node.state), actor)
                        actions = await self.environment.available_actions(deepcopy(node.state), actor)
                        if not actions or len({a.id for a in actions}) != len(actions):
                            raise ValueError("Nonterminal state has empty or duplicate legal actions")
                        contexts.append(DecisionContext(node.id, actor, observation, actions,
                                                        deepcopy(node.history), experiment.base_prompt))
                    max_children = sum(1 if config.mode == "sample" else min(config.branch_factor, len(c.actions)) for c in contexts)
                    if len(result.nodes) + max_children > config.max_nodes:
                        result.status = "node_budget"
                        break
                    batch = await self.policy.decide_many(contexts)
                    ids = [d.node_id for d in batch.decisions]
                    if len(ids) != len(set(ids)) or set(ids) != {n.id for n in frontier}:
                        raise ValueError("Policy must return exactly one decision per frontier node")
                    decision_map = {d.node_id: d for d in batch.decisions}
                    # Validate and calculate the entire round before committing any changes.
                    children, updates = [], []
                    for node, context in zip(frontier, contexts):
                        decision = decision_map[node.id].validate(context.actions)
                        ranked = sorted(decision.probabilities.items(), key=lambda kv: (-kv[1], kv[0]))
                        ranked = [(k, p) for k, p in ranked if p > 0]
                        if config.mode == "sample":
                            rng = random.Random(stable_seed(experiment.seed, node.id, "draw"))
                            draw, cumulative = rng.random(), 0.0
                            choice = ranked[-1]
                            for pair in ranked:
                                cumulative += pair[1]
                                if draw < cumulative:
                                    choice = pair
                                    break
                            selected = [choice]
                        else:
                            selected = ranked[:config.branch_factor]
                        for action_id, probability in selected:
                            actor = context.actor
                            action = next(a for a in context.actions if a.id == action_id)
                            new_state = await self.environment.step(deepcopy(node.state), action_id, actor)
                            outcome = await self.environment.terminal(deepcopy(new_state), actor)
                            observation_after = await self.environment.observe(deepcopy(new_state), actor)
                            depth = node.depth + 1
                            status = "terminal" if outcome else ("depth_limit" if depth >= config.depth else "active")
                            history = node.history + [{"step": depth, "action_id": action_id,
                                "action_description": action.description, "observation_before": context.observation,
                                "observation_after": observation_after, "probability": probability}]
                            child_id = f"{node.actor_id}/d{depth}/{stable_seed(node.id, action_id):016x}"
                            children.append(Node(child_id, node.actor_id, deepcopy(new_state), depth, node.id,
                                                 status, outcome, history, node.log_score + math.log(probability)))
                        updates.append((node, decision))
                    if config.mode == "lookahead":
                        for actor_id in actors:
                            active = sorted([n for n in children if n.actor_id == actor_id and n.status == "active"],
                                            key=lambda n: (-n.log_score, n.id))
                            for node in active[config.beam_width:]:
                                node.status = "pruned"
                    for node, decision in updates:
                        node.status = "expanded"
                        node.probabilities, node.confidence = decision.probabilities, decision.confidence
                        node.decision_metadata = decision.metadata
                    result.nodes.extend(children)
                    round_data = {"round": len(result.rounds) + 1, "depth": min(n.depth for n in frontier) + 1,
                                  "decisions": len(frontier), "children": len(children), "model": batch.model,
                                  "duration_ms": round(batch.duration_ms, 3), "input_tokens": batch.input_tokens,
                                  "requests": batch.requests, "round_ms": round((time.perf_counter() - started) * 1000, 3)}
                    result.rounds.append(round_data)
                    if self.checkpoint:
                        self.checkpoint(result)
                    for node, decision in updates:
                        self.emit("decision", {"node_id": node.id, "actor_id": node.actor_id,
                            "probabilities": decision.probabilities, "confidence": decision.confidence})
                    for node in children:
                        self.emit("transition", {"node_id": node.id, "parent_id": node.parent_id,
                            "actor_id": node.actor_id, "depth": node.depth, "action": node.history[-1]["action_id"],
                            "status": node.status, "outcome": node.outcome, "log_score": node.log_score})
                    self.emit("round", {**round_data, "summary": result.summary()})
        except TimeoutError:
            result.status, result.error = "timeout", "Run deadline reached; completed rounds preserved."
        except asyncio.CancelledError:
            result.status, result.error = "interrupted", "Run interrupted; completed rounds preserved."
        except Exception as exc:
            result.status = "error"
            result.error = safe_error(exc)
        finally:
            if self.checkpoint:
                self.checkpoint(result)
        self.emit("finished", result.summary())
        return result

def safe_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(safe_error(e) for e in exc.exceptions)
    return str(exc)
