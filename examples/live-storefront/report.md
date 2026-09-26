# Jev swarm experiment

Explore distinct actor goals through the controlled flow.

- Status: **completed**
- Decision policy: `jev:jev-1.13.0`
- Planner: `seeded-template`
- Mode: `sample`
- Actors: 4; evaluated decisions: 18; paths created: 22
- Terminal outcomes: {"success": 3}
- Depth-limited paths: 1; pruned paths: 0
- Provider requests: 5; reported input tokens: 9943
- Summed batch wall time: 32404.99 ms (not per-actor latency)

These are synthetic actor trajectories, not real customer conversion rates or causal evidence. Lookahead endpoints are correlated branches, not independent users. Path scores rank candidates; they are not calibrated probabilities of real futures.

## Actor paths

### actor-001: Budget 01

Goal: Find a suitable jacket with total cost at or below $110.

Traits: `{"budget_usd": 110, "priority": "budget", "patience": 0.698, "curiosity": 0.17}`

- field → add_field → checkout → purchase — **success**

### actor-002: Weather 02

Goal: Find waterproof protection for prolonged heavy rain.

Traits: `{"requires_waterproof": true, "priority": "weather", "patience": 0.443, "curiosity": 0.329}`

- ridge → compare → add_ridge → checkout → purchase — **success**

### actor-003: Speed 03

Goal: Get a jacket delivered within three days.

Traits: `{"delivery_deadline_days": 3, "priority": "speed", "patience": 0.766, "curiosity": 0.691}`

- field → add_field → checkout → purchase — **success**

### actor-004: Quality 04

Goal: Find durable weather protection, willing to pay up to $200.

Traits: `{"budget_usd": 200, "priority": "quality", "patience": 0.875, "curiosity": 0.22}`

- ridge → add_ridge → delivery → add_field → checkout — **depth_limit**
