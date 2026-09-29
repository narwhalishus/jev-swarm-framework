"""Measure Jev latency: connection setup vs server time, payload size and batch size.

Rebuilds real engine questions from the committed storefront trace, so payloads match what the
engine sends. Needs curl and TYPESAFE_API_KEY; the key reaches curl on stdin, never argv or disk.

    python -m examples.latency_probe [repetitions]
"""
from __future__ import annotations
import asyncio
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from jev_swarm import GraphEnvironment, JevPolicy, RunResult
from jev_swarm.models import DecisionContext

TRACE = Path(__file__).resolve().parent / "live-storefront" / "run.json"
URL = "https://api.typesafe.ai/v1/systemone"
TIMING = ('{"tls":%{time_appconnect},"ttfb":%{time_starttransfer},'
          '"total":%{time_total},"code":%{http_code}}')


def call(payload: dict, key: str, scratch: Path) -> dict:
    body, response = scratch / "body.json", scratch / "response.json"
    body.write_text(json.dumps(payload))
    config = f'header = "Authorization: Bearer {key}"\nheader = "Content-Type: application/json"\n'
    out = subprocess.run(["curl", "-sS", "-K", "-", "-o", str(response), "-w", TIMING,
                          "--data-binary", f"@{body}", URL],
                         input=config, capture_output=True, text=True, timeout=120, check=True)
    timing = json.loads(out.stdout)
    data = json.loads(response.read_text())
    timing.update(model=data.get("model"), input_tokens=data.get("usage", {}).get("input_tokens"),
                  bytes=body.stat().st_size, error=None if timing["code"] == 200 else str(data)[:300])
    return timing


async def engine_contexts() -> list[DecisionContext]:
    trace = RunResult.from_dict(json.loads(TRACE.read_text()))
    env = GraphEnvironment(trace.environment["spec"])
    actors = {a.id: a for a in trace.experiment.actors}
    contexts = []
    for node in trace.nodes:
        if node.status == "expanded":
            actor = actors[node.actor_id]
            contexts.append(DecisionContext(node.id, actor, await env.observe(node.state, actor),
                                            await env.available_actions(node.state, actor),
                                            node.history, trace.experiment.base_prompt))
    return sorted(contexts, key=lambda c: len(c.history))


def main() -> int:
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        print("Set TYPESAFE_API_KEY first.", file=sys.stderr)
        return 2
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    contexts = asyncio.run(engine_contexts())
    policy = JevPolicy(api_key=key, model="jev-latest")
    shallow, deep = contexts[0], contexts[-1]
    tiny = {"model": "jev-latest", "state": "My card was charged twice.",
            "questions": {"q0": {"type": "noul", "instructions": "Is the customer asking for a refund?"}}}
    cases = [
        ("tiny noul x1", tiny),
        (f"engine choice x1 (history {len(shallow.history)})", policy._payload([shallow])),
        (f"engine choice x1 (history {len(deep.history)})", policy._payload([deep])),
        ("engine choice x4 (deep)", policy._payload([deep] * 4)),
        ("engine choice x16 (deep)", policy._payload([deep] * 16)),
    ]
    with tempfile.TemporaryDirectory() as scratch:
        for name, payload in cases:
            rows = [call(payload, key, Path(scratch)) for _ in range(reps)]
            ok = [r for r in rows if r["code"] == 200]
            if not ok:
                print(f"{name}: failed: {rows[0]['error']}")
                continue
            median = lambda field: statistics.median(r[field] for r in ok)
            print(f"{name:34} {ok[0]['bytes']:6} B {ok[0]['input_tokens']:6} tok {ok[0]['model']} | "
                  f"median {median('total'):.2f}s, connect+TLS {median('tls'):.2f}s, "
                  f"server ~{median('ttfb') - median('tls'):.2f}s | all {[round(r['total'], 2) for r in rows]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
