"""Portable artifacts: full JSON trace, JSONL events, Markdown report, Graphviz DAG."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
from .models import JSON, RunResult

def save_json(path: str | Path, data: JSON) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)

def markdown_report(result: RunResult) -> str:
    s = result.summary()
    lines = ["# Jev swarm experiment", "", result.experiment.objective, "",
             f"- Status: **{result.status}**", f"- Decision policy: `{result.policy}`",
             f"- Planner: `{result.experiment.source}`", f"- Mode: `{result.config.mode}`",
             f"- Actors: {s['actors']}; evaluated decisions: {s['decisions']}; paths created: {s['nodes']}",
             f"- Terminal outcomes: {json.dumps(s['outcomes'])}",
             f"- Depth-limited paths: {s['depth_limited_paths']}; pruned paths: {s['pruned_paths']}",
             f"- Provider requests: {s['provider_requests']}; reported input tokens: {s['input_tokens']}",
             f"- Summed batch wall time: {s['provider_duration_ms']} ms (not per-actor latency)", "",
             "These are synthetic actor trajectories, not real customer conversion rates or causal evidence. "
             "Lookahead endpoints are correlated branches, not independent users. Path scores rank candidates; "
             "they are not calibrated probabilities of real futures.", ""]
    if result.error:
        lines += ["## Run error", "", result.error, ""]
    if result.policy == "offline-demo-heuristic":
        lines += ["**Offline demo:** no AI API was called. Decisions were produced by an explicit seeded heuristic.", ""]
    lines += ["## Actor paths", ""]
    for actor in result.experiment.actors:
        lines += [f"### {actor.id}: {actor.name}", "", f"Goal: {actor.goal}", "", f"Traits: `{json.dumps(actor.traits)}`", ""]
        nodes = [n for n in result.nodes if n.actor_id == actor.id and n.status in {"terminal", "depth_limit", "active"}]
        nodes.sort(key=lambda n: -n.log_score)
        for n in nodes[:8]:
            path = " → ".join(h["action_id"] for h in n.history) or "(initial state)"
            lines.append(f"- {path} — **{n.outcome or n.status}**")
        if len(nodes) > 8:
            lines.append(f"- {len(nodes)-8} additional paths are in run.json.")
        lines.append("")
    return "\n".join(lines)

def graphviz(result: RunResult) -> str:
    quote = lambda s: json.dumps(str(s))
    lines = ['digraph swarm {', '  rankdir=LR;', '  graph [bgcolor="white"];',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fillcolor="#eef2f6"];']
    for actor in result.experiment.actors:
        lines += [f'  subgraph {quote("cluster_"+actor.id)} {{', f'    label={quote(actor.id+": "+actor.name)};']
        for n in result.nodes:
            if n.actor_id != actor.id:
                continue
            label = f"d{n.depth} · {n.state.get('node', 'state')}\n{n.outcome or n.status}"
            color = '#c9f7d9' if n.outcome == 'success' else '#f7d5cf' if n.status == 'terminal' else '#eeeeee' if n.status == 'pruned' else '#e3ecfb'
            lines.append(f'    {quote(n.id)} [label={quote(label)}, fillcolor="{color}"];')
            if n.parent_id:
                h = n.history[-1]
                lines.append(f'    {quote(n.parent_id)} -> {quote(n.id)} [label={quote(h["action_id"]+" · "+format(h["probability"],".2f"))}];')
        lines.append('  }')
    return '\n'.join(lines + ['}']) + '\n'

def export_run(result: RunResult, directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    save_json(directory / 'run.json', result.to_dict())
    save_json(directory / 'summary.json', result.summary())
    save_json(directory / 'experiment.json', asdict(result.experiment))
    (directory / 'report.md').write_text(markdown_report(result))
    (directory / 'tree.dot').write_text(graphviz(result))
    from .viewer import viewer_html
    (directory / 'viewer.html').write_text(viewer_html(result))
