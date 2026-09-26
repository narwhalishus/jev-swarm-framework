# Jev swarm experiment

Explore how user goals shape onboarding journeys.

- Status: **completed**
- Decision policy: `jev:jev-1.13.0`
- Planner: `seeded-template`
- Mode: `lookahead`
- Actors: 3; evaluated decisions: 20; paths created: 41
- Terminal outcomes: {"exit": 9, "success": 4}
- Depth-limited paths: 2; pruned paths: 6
- Provider requests: 4; reported input tokens: 9004
- Summed batch wall time: 20897.54 ms (not per-actor latency)

These are synthetic actor trajectories, not real customer conversion rates or causal evidence. Lookahead endpoints are correlated branches, not independent users. Path scores rank candidates; they are not calibrated probabilities of real futures.

## Actor paths

### actor-001: Speed 01

Goal: Complete a first useful task with minimal setup.

Traits: `{"priority": "speed", "patience": 0.698, "curiosity": 0.17}`

- sample → create → create → task — **success**
- start → create → task — **success**
- sample → leave — **exit**
- sample → create → leave — **exit**
- start → leave — **exit**

### actor-002: Research 02

Goal: Understand workflow and feature limitations before adopting the tool.

Traits: `{"priority": "research", "patience": 0.443, "curiosity": 0.329}`

- pricing → guide → create → task — **success**
- sample → create → docs → create — **depth_limit**
- sample → create → docs → leave — **exit**
- sample → create → leave — **exit**
- pricing → guide → leave — **exit**
- pricing → guide → create → leave — **exit**

### actor-003: Budget 03

Goal: Evaluate the product on the free plan without incurring charges.

Traits: `{"priority": "budget", "patience": 0.766, "curiosity": 0.691}`

- pricing → free → create → task — **success**
- sample → pricing → free → create — **depth_limit**
- sample → pricing → free → leave — **exit**
- pricing → free → create → leave — **exit**
