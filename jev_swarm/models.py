"""Public, JSON-serializable contracts. No provider or UI dependency."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any
import math

JSON = dict[str, Any]

@dataclass(frozen=True)
class Action:
    id: str
    description: str
    metadata: JSON = field(default_factory=dict)

@dataclass(frozen=True)
class Actor:
    id: str
    goal: str
    traits: JSON = field(default_factory=dict)
    name: str = ""

@dataclass
class Experiment:
    objective: str
    base_prompt: str
    actors: list[Actor]
    seed: int = 42
    source: str = "manual"
    hypothesis: str = ""

    def validate(self) -> None:
        if not self.objective.strip() or not self.base_prompt.strip():
            raise ValueError("Objective and base_prompt must be nonempty")
        if not 1 <= len(self.actors) <= 128:
            raise ValueError("Provide 1–128 actors")
        ids = [a.id for a in self.actors]
        if len(set(ids)) != len(ids) or any(not x for x in ids):
            raise ValueError("Actor IDs must be nonempty and unique")
        if any(not a.goal.strip() for a in self.actors):
            raise ValueError("Every actor needs a goal")

    @classmethod
    def from_dict(cls, data: JSON) -> Experiment:
        result = cls(**{**data, "actors": [Actor(**a) for a in data["actors"]]})
        result.validate()
        return result

@dataclass(frozen=True)
class DecisionContext:
    node_id: str
    actor: Actor
    observation: JSON
    actions: list[Action]
    history: list[JSON]
    base_prompt: str

@dataclass
class Decision:
    node_id: str
    probabilities: dict[str, float]
    confidence: float | None = None
    metadata: JSON = field(default_factory=dict)

    def validate(self, actions: list[Action]) -> Decision:
        ids = [a.id for a in actions]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Legal actions must be nonempty and unique")
        if set(self.probabilities) != set(ids):
            raise ValueError("Decision keys must exactly match the legal actions")
        values = list(self.probabilities.values())
        if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 or p > 1 for p in values):
            raise ValueError("Decision probabilities must be finite numbers in [0,1]")
        total = sum(values)
        if total <= 0 or abs(total - 1) > 0.02:
            raise ValueError("Decision distribution must sum to 1 (within 0.02 rounding tolerance)")
        if self.confidence is not None and (not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("Confidence must be in [0,1]")
        return Decision(self.node_id, {k: v / total for k, v in self.probabilities.items()}, self.confidence,
                        {**self.metadata, "raw_probability_sum": total})

@dataclass
class BatchResult:
    decisions: list[Decision]
    model: str
    duration_ms: float = 0
    input_tokens: int = 0
    requests: int = 0

@dataclass
class RunConfig:
    depth: int = 6
    mode: str = "sample"
    branch_factor: int = 3
    beam_width: int = 3
    max_decisions: int = 1000
    max_nodes: int = 3000
    timeout_seconds: float = 120
    supervise_every: int = 0

    def validate(self) -> None:
        if not isinstance(self.supervise_every, int) or self.supervise_every < 0:
            raise ValueError("supervise_every must be a nonnegative integer")
        if self.mode not in {"sample", "lookahead"}:
            raise ValueError("mode must be sample or lookahead")
        if not 1 <= self.depth <= 100:
            raise ValueError("depth must be 1–100")
        if not 1 <= self.branch_factor <= 20 or not 1 <= self.beam_width <= 100:
            raise ValueError("branch_factor must be 1–20; beam_width 1–100")
        if self.max_decisions < 1 or self.max_nodes < 1:
            raise ValueError("Resource budgets must be positive")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")

@dataclass
class Node:
    id: str
    actor_id: str
    state: JSON
    depth: int = 0
    parent_id: str | None = None
    status: str = "active"
    outcome: str | None = None
    history: list[JSON] = field(default_factory=list)
    log_score: float = 0.0
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    decision_metadata: JSON = field(default_factory=dict)

@dataclass
class RunResult:
    experiment: Experiment
    config: RunConfig
    environment: JSON
    nodes: list[Node] = field(default_factory=list)
    rounds: list[JSON] = field(default_factory=list)
    status: str = "running"
    error: str | None = None
    created_at: str = ""
    schema_version: int = 1
    policy: str = ""
    supervision: list[JSON] = field(default_factory=list)

    def to_dict(self) -> JSON:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JSON) -> RunResult:
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported trace schema version")
        result = cls(**{**data, "experiment": Experiment.from_dict(data["experiment"]),
                       "config": RunConfig(**data["config"]), "nodes": [Node(**n) for n in data["nodes"]]})
        result.config.validate()
        return result

    def summary(self) -> JSON:
        endpoints = [n for n in self.nodes if n.status == "terminal"]
        outcomes: dict[str, int] = {}
        for n in endpoints:
            key = n.outcome or "unknown"
            outcomes[key] = outcomes.get(key, 0) + 1
        return {
            "status": self.status, "mode": self.config.mode, "policy": self.policy,
            "actors": len(self.experiment.actors), "rounds": len(self.rounds),
            "decisions": sum(r["decisions"] for r in self.rounds),
            "nodes": len(self.nodes), "terminal_paths": len(endpoints), "outcomes": outcomes,
            "pruned_paths": sum(n.status in {"pruned", "supervisor_pruned"} for n in self.nodes),
            "supervision_checks": len(self.supervision),
            "depth_limited_paths": sum(n.status == "depth_limit" for n in self.nodes),
            "unfinished_paths": sum(n.status in {"active", "budget_limit"} for n in self.nodes),
            "input_tokens": sum(r.get("input_tokens", 0) for r in self.rounds),
            "provider_requests": sum(r.get("requests", 0) for r in self.rounds),
            "provider_duration_ms": round(sum(r.get("duration_ms", 0) for r in self.rounds), 2),
            "interpretation": "Synthetic path counts, not measured human conversion or causal lift. Beam scores are heuristic rankings.",
        }
