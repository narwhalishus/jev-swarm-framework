"""Environment boundary: snapshots are independent JSON values, transitions are controlled."""
from __future__ import annotations
from copy import deepcopy
from typing import Protocol
from .models import Action, Actor, JSON

class Environment(Protocol):
    def describe(self) -> JSON: ...
    async def reset(self, actor: Actor, seed: int) -> JSON: ...
    async def observe(self, state: JSON, actor: Actor) -> JSON: ...
    async def available_actions(self, state: JSON, actor: Actor) -> list[Action]: ...
    async def step(self, state: JSON, action_id: str, actor: Actor) -> JSON: ...
    async def terminal(self, state: JSON, actor: Actor) -> str | None: ...

class GraphEnvironment:
    """A finite-state environment loaded from JSON. No browser or external effects.

    Transition destinations are not exposed to the actor policy. Each step returns
    a fresh state; a branch never mutates siblings. Fields in observation may
    contain structured data such as cart contents or available products.
    """
    def __init__(self, spec: JSON):
        self.spec = deepcopy(spec)
        if not isinstance(spec.get("states"), list) or not spec["states"]:
            raise ValueError("Environment needs a nonempty states list")
        self.states = {s["id"]: s for s in self.spec["states"]}
        if len(self.states) != len(self.spec["states"]):
            raise ValueError("State IDs must be unique")
        if self.spec.get("initial_state") not in self.states:
            raise ValueError("Unknown initial_state")
        for state in self.states.values():
            if not isinstance(state.get("observation"), (str, dict)):
                raise ValueError("Every state needs a string or object observation")
            actions = state.get("actions", [])
            ids = [a["id"] for a in actions]
            if len(set(ids)) != len(ids) or any(not x for x in ids):
                raise ValueError("Action IDs must be nonempty and unique per state")
            if state.get("outcome") and actions:
                raise ValueError("Terminal states cannot expose actions")
            if not state.get("outcome") and not actions:
                raise ValueError("Nonterminal states require actions")
            for action in actions:
                if action.get("to") not in self.states:
                    raise ValueError(f"Unknown destination: {action.get('to')}")
                if not isinstance(action.get("description"), str):
                    raise ValueError("Every action requires a description")

    def describe(self) -> JSON:
        return {"adapter": "graph", "spec": deepcopy(self.spec)}

    async def reset(self, actor: Actor, seed: int) -> JSON:
        return {"node": self.spec["initial_state"], "variables": deepcopy(self.spec.get("initial_variables", {}))}

    async def observe(self, state: JSON, actor: Actor) -> JSON:
        return {"screen": self.states[state["node"]].get("label", state["node"]),
                "content": deepcopy(self.states[state["node"]]["observation"]),
                "variables": deepcopy(state.get("variables", {}))}

    async def available_actions(self, state: JSON, actor: Actor) -> list[Action]:
        return [Action(a["id"], a["description"], {"label": a.get("label", a["id"]), "tags": a.get("tags", [])})
                for a in self.states[state["node"]].get("actions", [])]

    async def step(self, state: JSON, action_id: str, actor: Actor) -> JSON:
        action = next((a for a in self.states[state["node"]].get("actions", []) if a["id"] == action_id), None)
        if not action:
            raise ValueError(f"Illegal action {action_id!r} for state {state['node']!r}")
        result = deepcopy(state)
        result["node"] = action["to"]
        result.setdefault("variables", {}).update(deepcopy(action.get("set", {})))
        return result

    async def terminal(self, state: JSON, actor: Actor) -> str | None:
        return self.states[state["node"]].get("outcome")
