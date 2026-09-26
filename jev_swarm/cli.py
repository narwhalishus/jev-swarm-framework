from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from .engine import SwarmRunner
from .environment import GraphEnvironment
from .export import export_run, save_json
from .models import Experiment, RunConfig, RunResult
from .planner import FrontierPlanner, seeded_experiment
from .policies import DemoPolicy, JevPolicy

def load(path):
    return json.loads(Path(path).read_text())

def add_frontier(p):
    p.add_argument('--planner', choices=['seeded','bedrock','anthropic','compatible'], default='seeded')
    p.add_argument('--aws-region', help='Bedrock region; defaults to AWS_REGION / AWS_DEFAULT_REGION / us-east-1')
    p.add_argument('--bedrock-keychain', default='bedrock-token-acct-a', help='Exact macOS Keychain service name')
    p.add_argument('--frontier-model', help='Model ID, or set FRONTIER_MODEL')
    p.add_argument('--frontier-base-url', help='Compatible HTTPS endpoint root, e.g. https://provider.example/v1')

def frontier(args):
    if args.planner == 'seeded':
        raise ValueError('Frontier oversight needs --planner bedrock, anthropic or compatible')
    return FrontierPlanner(provider=args.planner, model=args.frontier_model, base_url=args.frontier_base_url, region=args.aws_region, keychain_service=args.bedrock_keychain)

def parser():
    p = argparse.ArgumentParser(description='Jev swarm: controlled synthetic actors, sampled rollouts and bounded lookahead.')
    sub = p.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Create an editable experiment and diverse actor profiles')
    run = sub.add_parser('run', help='Run N actors for D decisions')
    for cmd in (plan, run):
        cmd.add_argument('--environment', default='examples/storefront.json')
        cmd.add_argument('--objective', default='Explore how differing user goals shape paths through the experience.')
        cmd.add_argument('-n','--actors', type=int, default=8)
        cmd.add_argument('--seed', type=int, default=42)
        add_frontier(cmd)
    plan.add_argument('--out', default='experiment.json')
    run.add_argument('--experiment', help='Load a saved plan instead of generating one')
    run.add_argument('--resume', help='Resume run.json from a completed round (uses its settings and graph)')
    run.add_argument('--policy', choices=['demo','jev'], default='demo')
    run.add_argument('--jev-model', default='jev-latest')
    run.add_argument('--mode', choices=['sample','lookahead'], default='sample')
    run.add_argument('-d','--depth', type=int, default=6)
    run.add_argument('--branch-factor', type=int, default=3)
    run.add_argument('--beam-width', type=int, default=3)
    run.add_argument('--max-decisions', type=int, default=1000)
    run.add_argument('--max-nodes', type=int, default=3000)
    run.add_argument('--timeout', type=float, default=120)
    run.add_argument('--batch-size', type=int, default=16)
    run.add_argument('--concurrency', type=int, default=4)
    run.add_argument('--out', help='Output directory; defaults to a unique directory in runs/')
    run.add_argument('--supervise-every', type=int, default=0, help='Frontier checks every N rounds; 0 disables')
    run.add_argument('--review', action='store_true', help='Ask frontier to review the completed synthetic run')
    run.add_argument('--overwrite', action='store_true', help='Allow replacing known output files in an existing directory')
    watch = sub.add_parser('watch', help='Read-only live trace viewer on localhost')
    watch.add_argument('trace', help='run.json path or run directory')
    watch.add_argument('--port', type=int, default=8765)
    report = sub.add_parser('report', help='Print summary or regenerate artifacts from run.json')
    report.add_argument('trace')
    report.add_argument('--out')
    return p

async def execute(args):
    if args.command == 'report':
        result = RunResult.from_dict(load(args.trace))
        print(json.dumps(result.summary(), indent=2))
        if args.out:
            export_run(result,args.out)
        return 0
    resume = None
    if args.command == 'run' and args.resume:
        resume = RunResult.from_dict(load(args.resume))
        if resume.environment.get('adapter') != 'graph':
            raise ValueError('CLI resume supports graph environments; use the Python API for custom adapters')
        env = GraphEnvironment(resume.environment['spec'])
        experiment, config = resume.experiment, resume.config
        if resume.policy.startswith('jev:'):
            args.policy, args.jev_model = 'jev', resume.policy[4:]
        else:
            args.policy = 'demo'
    else:
        env = GraphEnvironment(load(args.environment))
        if args.command == 'run' and args.experiment:
            experiment = Experiment.from_dict(load(args.experiment))
        elif args.planner == 'seeded':
            experiment = seeded_experiment(args.objective,args.actors,args.seed,env.describe())
        else:
            print(f'Planning {args.actors} actors with frontier model…', flush=True)
            experiment = await frontier(args).plan(args.objective,args.actors,args.seed,env.describe())
        config = None
    if args.command == 'plan':
        save_json(args.out, asdict(experiment))
        print(f'Saved {len(experiment.actors)} actors to {args.out} ({experiment.source}).')
        return 0
    config = config or RunConfig(args.depth,args.mode,args.branch_factor,args.beam_width,args.max_decisions,args.max_nodes,args.timeout,args.supervise_every)
    config.validate()
    supervisor = frontier(args) if config.supervise_every else None
    policy = DemoPolicy(experiment.seed) if args.policy == 'demo' else JevPolicy(model=args.jev_model,batch_size=args.batch_size,concurrency=args.concurrency)
    out = Path(args.out or ('runs/'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')))
    if (out/'run.json').exists() and not args.overwrite:
        raise ValueError(f'{out}/run.json already exists. Choose a new directory or pass --overwrite.')
    out.mkdir(parents=True,exist_ok=True)
    print(f'{len(experiment.actors)} actors · depth {config.depth} · {config.mode} · {policy.name}',flush=True)
    if args.policy == 'demo':
        print('OFFLINE ACTOR POLICY: seeded heuristic only; no Jev decision calls.',flush=True)
    with (out/'events.jsonl').open('w') as events:
        def emit(kind,payload):
            events.write(json.dumps({'event':kind,**payload},allow_nan=False)+'\n')
            events.flush()
            if kind == 'round':
                summary=payload['summary']
                print(f"  round {payload['round']:02} | {payload['decisions']:3} decisions | {payload['children']:3} branches | {summary['terminal_paths']:3} endpoints | {payload['round_ms']:.1f} ms",flush=True)
            elif kind == 'supervision':
                print(f"  frontier: {payload['action']} | {len(payload['prune_node_ids'])} pruned | {payload['reason']}", flush=True)
        runner = SwarmRunner(env,policy,on_event=emit,checkpoint=lambda r:save_json(out/'run.json',r.to_dict()), supervisor=supervisor.supervise if supervisor else None)
        result = await runner.run(experiment,config,resume=resume)
    export_run(result,out)
    print(json.dumps(result.summary(),indent=2))
    print(f'Artifacts: {out.resolve()}')
    if result.error:
        print(f'Run issue: {result.error}',file=sys.stderr)
    if args.review:
        try:
            review=await frontier(args).review(result)
            (out/'frontier-review.md').write_text(review+'\n')
            print('\nFrontier review:\n'+review)
        except Exception as exc:
            print(f'Review unavailable: {exc}. Simulation artifacts preserved.',file=sys.stderr)
            return 2
    return 0 if result.status == 'completed' else 2

def main():
    args=parser().parse_args()
    try:
        if args.command == 'watch':
            from .viewer import serve_trace
            serve_trace(args.trace,args.port)
            return
        code=asyncio.run(execute(args))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        code=2
    except KeyboardInterrupt:
        print('Interrupted. Completed rounds are saved in the output directory.',file=sys.stderr)
        code=130
    except Exception as exc:
        print(f'Error: {exc}',file=sys.stderr)
        code=2
    raise SystemExit(code)
