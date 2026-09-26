import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from jev_swarm.credentials import bedrock_token
from jev_swarm.viewer import viewer_html

from jev_swarm import (Action,Actor,BatchResult,Decision,DecisionContext,Experiment,GraphEnvironment,
    SwarmRunner,RunConfig,RunResult,DemoPolicy,JevPolicy,FrontierPlanner,seeded_experiment,export_run)

SPEC={'id':'test','name':'Test flow','initial_state':'start','states':[
 {'id':'start','observation':'Choose a path','actions':[
     {'id':'a','description':'Take path A','to':'middle','set':{'choice':'A'}},
     {'id':'b','description':'Take path B','to':'middle','set':{'choice':'B'}},
     {'id':'leave','description':'End the session','to':'exit'}]},
 {'id':'middle','observation':'Finish or reconsider','actions':[
     {'id':'finish','description':'Finish the task','to':'done'},
     {'id':'back','description':'Reconsider','to':'start'}]},
 {'id':'done','observation':'Completed','outcome':'success','actions':[]},
 {'id':'exit','observation':'Ended','outcome':'exit','actions':[]}]}

def experiment(n=3):
    return Experiment('Test isolated actors','Pursue your own goal.',[
        Actor(f'a{i}',f'Private goal {i}',{'patience':.6,'curiosity':.5,'priority':'speed'}) for i in range(n)],42)

class Uniform:
    name='uniform'
    def __init__(self):self.calls=[]
    async def decide_many(self,contexts):
        self.calls.append(deepcopy(contexts))
        return BatchResult([Decision(c.node_id,{a.id:1/len(c.actions) for a in c.actions}) for c in contexts],self.name)

class FakeTransport:
    def __init__(self,responder):self.responder=responder;self.calls=[]
    async def post(self,url,headers,payload,timeout):
        self.calls.append((url,deepcopy(headers),deepcopy(payload),timeout))
        return self.responder(payload)

def jev_response(payload):
    return {'model':'jev-test','usage':{'input_tokens':123},'answers':{
        key:{'type':'choice','probabilities':{a:1/len(q['criteria']) for a in q['criteria']},'confidence':.2}
        for key,q in payload['questions'].items()}}

class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_exactly_one_path_per_actor(self):
        p=Uniform();r=await SwarmRunner(GraphEnvironment(SPEC),p).run(experiment(),RunConfig(depth=4))
        self.assertEqual(r.status,'completed')
        for a in r.experiment.actors:
            leaves=[n for n in r.nodes if n.actor_id==a.id and n.status in {'terminal','depth_limit'}]
            self.assertEqual(len(leaves),1)
            self.assertLessEqual(leaves[0].depth,4)

    async def test_terminal_not_evaluated(self):
        spec=deepcopy(SPEC);spec['initial_state']='done';p=Uniform()
        r=await SwarmRunner(GraphEnvironment(spec),p).run(experiment())
        self.assertEqual(len(p.calls),0)
        self.assertEqual(r.summary()['outcomes'],{'success':3})

    async def test_seed_reproducible(self):
        a=await SwarmRunner(GraphEnvironment(SPEC),DemoPolicy(42)).run(experiment(),RunConfig(depth=7))
        b=await SwarmRunner(GraphEnvironment(SPEC),DemoPolicy(42)).run(experiment(),RunConfig(depth=7))
        self.assertEqual([asdict(n) for n in a.nodes],[asdict(n) for n in b.nodes])

    async def test_beam_limits_and_prunes(self):
        p=Uniform();r=await SwarmRunner(GraphEnvironment(SPEC),p).run(experiment(),RunConfig(depth=6,mode='lookahead',branch_factor=3,beam_width=1))
        self.assertGreater(r.summary()['pruned_paths'],0)
        for batch in p.calls:
            for a in r.experiment.actors:
                self.assertLessEqual(sum(c.actor.id==a.id for c in batch),1)

    async def test_children_are_isolated(self):
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform()).run(experiment(1),RunConfig(depth=2,mode='lookahead'))
        children=[n for n in r.nodes if n.depth==1 and n.state['node']=='middle']
        self.assertEqual({n.state['variables']['choice'] for n in children},{'A','B'})
        children[0].state['variables']['choice']='changed'
        self.assertNotEqual(children[1].state['variables']['choice'],'changed')
        self.assertEqual(r.nodes[0].state['variables'],{})

    async def test_history_and_private_goals_isolated(self):
        p=Uniform();r=await SwarmRunner(GraphEnvironment(SPEC),p).run(experiment(),RunConfig(depth=4,mode='lookahead'))
        for batch in p.calls:
            for c in batch:
                node=next(n for n in r.nodes if n.id==c.node_id)
                self.assertEqual(len(c.history),node.depth)
                self.assertEqual(c.actor.id,node.actor_id)
                self.assertNotIn('future',c.observation)

    async def test_invalid_action_distribution_rejected(self):
        class Bad(Uniform):
            async def decide_many(self,cs):return BatchResult([Decision(c.node_id,{'illegal':1.}) for c in cs],'bad')
        r=await SwarmRunner(GraphEnvironment(SPEC),Bad()).run(experiment())
        self.assertEqual(r.status,'error');self.assertEqual(len(r.rounds),0)
        self.assertTrue(all(n.status=='active' for n in r.nodes))

    async def test_partial_batch_rejected_atomically(self):
        class Bad(Uniform):
            async def decide_many(self,cs):return BatchResult([Decision(cs[0].node_id,{a.id:1/len(cs[0].actions) for a in cs[0].actions})],'bad')
        r=await SwarmRunner(GraphEnvironment(SPEC),Bad()).run(experiment())
        self.assertEqual(r.status,'error');self.assertEqual(len(r.nodes),3)

    async def test_budget_stops_before_api_call(self):
        p=Uniform();r=await SwarmRunner(GraphEnvironment(SPEC),p).run(experiment(),RunConfig(max_decisions=2))
        self.assertEqual(r.status,'decision_budget');self.assertEqual(p.calls,[])
        p=Uniform();r=await SwarmRunner(GraphEnvironment(SPEC),p).run(experiment(),RunConfig(max_nodes=4))
        self.assertEqual(r.status,'node_budget');self.assertEqual(p.calls,[])

    async def test_cycle_stops_at_depth(self):
        spec={'initial_state':'loop','states':[{'id':'loop','observation':'Again','actions':[{'id':'again','description':'Repeat','to':'loop'}]}]}
        r=await SwarmRunner(GraphEnvironment(spec),Uniform()).run(experiment(1),RunConfig(depth=5))
        self.assertEqual(r.summary()['depth_limited_paths'],1)
        self.assertEqual(r.summary()['decisions'],5)

    async def test_timeout_preserves_roots(self):
        class Slow(Uniform):
            async def decide_many(self,cs):await asyncio.sleep(1)
        r=await SwarmRunner(GraphEnvironment(SPEC),Slow()).run(experiment(),RunConfig(timeout_seconds=.02))
        self.assertEqual(r.status,'timeout');self.assertEqual(len(r.nodes),3)

    async def test_resume_matches_uninterrupted_run(self):
        class FailOnce(Uniform):
            async def decide_many(self,cs):
                if len(self.calls)==1:raise ValueError('temporary test failure')
                return await super().decide_many(cs)
        config=RunConfig(depth=5,mode='lookahead');env=GraphEnvironment(SPEC)
        partial=await SwarmRunner(env,FailOnce()).run(experiment(),config)
        self.assertEqual(partial.status,'error');self.assertEqual(len(partial.rounds),1)
        checkpoint=RunResult.from_dict(partial.to_dict())
        resumed=await SwarmRunner(env,Uniform()).run(checkpoint.experiment,checkpoint.config,resume=checkpoint)
        full=await SwarmRunner(env,Uniform()).run(experiment(),config)
        self.assertEqual([asdict(n) for n in resumed.nodes],[asdict(n) for n in full.nodes])

    async def test_resume_rejects_environment_mismatch(self):
        result=await SwarmRunner(GraphEnvironment(SPEC),Uniform()).run(experiment())
        spec=deepcopy(SPEC);spec['name']='Changed'
        with self.assertRaises(ValueError):await SwarmRunner(GraphEnvironment(spec),Uniform()).run(result.experiment,result.config,resume=result)

    async def test_exports_are_readable_and_complete(self):
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform()).run(experiment())
        with tempfile.TemporaryDirectory() as d:
            export_run(r,d)
            data=json.loads((Path(d)/'run.json').read_text())
            self.assertEqual(RunResult.from_dict(data).summary(),r.summary())
            self.assertIn('digraph swarm',(Path(d)/'tree.dot').read_text())
            self.assertIn('synthetic',(Path(d)/'report.md').read_text())

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def contexts(self,n=3):
        return [DecisionContext(f'n{i}',Actor(f'a{i}',f'PRIVATE-{i}'),{'current':'screen'},
                [Action('yes','Continue'),Action('no','Leave')],[],'shared-base') for i in range(n)]

    async def test_jev_contract_and_batching(self):
        t=FakeTransport(jev_response);p=JevPolicy(api_key='test-secret',batch_size=2,transport=t)
        r=await p.decide_many(self.contexts(5))
        self.assertEqual(len(t.calls),3);self.assertEqual(len(r.decisions),5)
        self.assertEqual(r.input_tokens,369)
        for url,headers,payload,_ in t.calls:
            self.assertEqual(url,'https://api.typesafe.ai/v1/systemone')
            self.assertEqual(headers['Authorization'],'Bearer test-secret')
            self.assertEqual(payload['state'],{'base_prompt':'shared-base'})
            for q in payload['questions'].values():
                text=json.dumps(q);self.assertEqual(text.count('PRIVATE-'),1)
                self.assertEqual(set(q['criteria']),{'yes','no'})

    async def test_provider_invalid_answer_fails(self):
        t=FakeTransport(lambda p:{'answers':{}})
        with self.assertRaises(ExceptionGroup):await JevPolicy(api_key='test',transport=t).decide_many(self.contexts())

    async def test_oversized_context_rejected_before_http(self):
        cs=self.contexts(1);cs[0].observation['huge']='x'*5000;t=FakeTransport(jev_response)
        with self.assertRaises(ValueError):await JevPolicy(api_key='test',transport=t,max_batch_bytes=1000).decide_many(cs)
        self.assertEqual(len(t.calls),0)

    async def test_frontier_plan_contract(self):
        plan={'base_prompt':'Pursue your goals in the controlled environment.', 'hypothesis':'Test paths', 'actors':[
            {'name':'One','goal':'Finish quickly','traits':{'priority':'speed','patience':.3,'curiosity':.2}},
            {'name':'Two','goal':'Compare first','traits':{'priority':'research','patience':.8,'curiosity':.9}}]}
        t=FakeTransport(lambda p:{'content':[{'type':'tool_use','name':'submit_plan','input':plan}]})
        result=await FrontierPlanner(api_key='test',model='test-model',transport=t).plan('Test',2,42,{'spec':SPEC})
        self.assertEqual(len(result.actors),2);self.assertEqual(result.actors[0].id,'actor-001')
        self.assertEqual(t.calls[0][2]['tool_choice'],{'type':'tool','name':'submit_plan'})
        self.assertNotIn('test-secret',json.dumps(asdict(result)))

    async def test_compatible_frontier(self):
        plan={'base_prompt':'Use this actor goal.', 'actors':[{'goal':'Finish','traits':{'patience':.5,'curiosity':.5}}]}
        t=FakeTransport(lambda p:{'choices':[{'message':{'content':json.dumps(plan)}}]})
        p=FrontierPlanner(provider='compatible',api_key='test',model='gateway-model',base_url='https://example.test/v1',transport=t)
        result=await p.plan('Test',1,42,{'spec':SPEC})
        self.assertEqual(result.source,'compatible:gateway-model')
        self.assertEqual(t.calls[0][0],'https://example.test/v1/chat/completions')

    async def test_bedrock_plan_supervision_and_review(self):
        plan={'base_prompt':'Pursue your own goal.', 'actors':[
            {'name':'One','goal':'Finish','traits':{'patience':.5,'curiosity':.5}}]}
        def respond(payload):
            if 'toolConfig' not in payload:
                return {'output':{'message':{'content':[{'text':'Observed synthetic paths only.'}]}}}
            name=payload['toolConfig']['toolChoice']['tool']['name']
            value=plan if name=='submit_plan' else {'action':'continue','prune_node_ids':[],'reason':'Explore remaining paths.'}
            return {'output':{'message':{'content':[{'toolUse':{'name':name,'input':value}}]}}}
        t=FakeTransport(respond)
        p=FrontierPlanner(provider='bedrock',api_key='test-bedrock-secret',model='model:version',region='us-west-2',transport=t)
        exp=await p.plan('Test',1,42,{'spec':SPEC})
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform()).run(exp,RunConfig(depth=3))
        self.assertEqual((await p.supervise(r))['action'],'continue')
        self.assertEqual(await p.review(r),'Observed synthetic paths only.')
        url,headers,payload,_=t.calls[0]
        self.assertEqual(url,'https://bedrock-runtime.us-west-2.amazonaws.com/model/model%3Aversion/converse')
        self.assertEqual(headers,{'Authorization':'Bearer test-bedrock-secret'})
        self.assertIn('json',payload['toolConfig']['tools'][0]['toolSpec']['inputSchema'])
        self.assertNotIn('test-bedrock-secret',json.dumps(r.to_dict()))

class OversightTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_retries_pending_supervision_before_more_decisions(self):
        async def unavailable(snapshot):
            raise ValueError('Supervisor temporarily unavailable')
        config=RunConfig(depth=4,mode='lookahead',supervise_every=1)
        env=GraphEnvironment(SPEC)
        partial=await SwarmRunner(env,Uniform(),supervisor=unavailable).run(experiment(1),config)
        self.assertEqual(partial.status,'error')
        self.assertEqual(len(partial.rounds),1)
        rounds_seen=[]
        async def recovered(snapshot):
            rounds_seen.append(len(snapshot.rounds))
            return {'action':'stop','prune_node_ids':[],'reason':'Inspect before proceeding.'}
        policy=Uniform()
        resumed=await SwarmRunner(env,policy,supervisor=recovered).run(
            partial.experiment,partial.config,resume=partial)
        self.assertEqual(rounds_seen,[1])
        self.assertEqual(policy.calls,[])
        self.assertEqual(resumed.status,'supervisor_stopped')

    async def test_continue_supervision_runs_once_per_round(self):
        rounds_seen=[]
        async def supervise(snapshot):
            rounds_seen.append(len(snapshot.rounds))
            return {'action':'continue','prune_node_ids':[],'reason':'Continue exploration.'}
        result=await SwarmRunner(GraphEnvironment(SPEC),Uniform(),supervisor=supervise).run(
            experiment(1),RunConfig(depth=4,mode='lookahead',supervise_every=1))
        self.assertEqual(result.status,'completed')
        self.assertEqual(rounds_seen,[1,2,3])

    async def test_stop_and_prune_preserve_completed_round(self):
        async def supervise(snapshot):
            target=next(n.id for n in snapshot.nodes if n.status=='active')
            snapshot.nodes.clear()  # The supervisor receives an isolated copy.
            return {'action':'stop','prune_node_ids':[target],'reason':'Stop for inspection.'}
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform(),supervisor=supervise).run(
            experiment(2),RunConfig(depth=5,mode='lookahead',supervise_every=1))
        self.assertEqual(r.status,'supervisor_stopped')
        self.assertEqual(len(r.rounds),1)
        self.assertEqual(sum(n.status=='supervisor_pruned' for n in r.nodes),1)
        self.assertEqual(len(r.supervision),1)
        self.assertGreater(len(r.nodes),2)
        self.assertEqual(RunResult.from_dict(r.to_dict()).supervision,r.supervision)

    async def test_invalid_pruning_cannot_modify_completed_nodes(self):
        async def supervise(snapshot):
            return {'action':'continue','prune_node_ids':[snapshot.nodes[0].id],'reason':'Invalid target.'}
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform(),supervisor=supervise).run(
            experiment(1),RunConfig(depth=3,mode='lookahead',supervise_every=1))
        self.assertEqual(r.status,'error')
        self.assertEqual(len(r.rounds),1)
        self.assertEqual(r.supervision,[])
        self.assertEqual(r.nodes[0].status,'expanded')

    async def test_viewer_embedded_data_cannot_close_script(self):
        exp=experiment(1);exp.objective='</script><script>alert(1)</script>'
        r=await SwarmRunner(GraphEnvironment(SPEC),Uniform()).run(exp)
        html=viewer_html(r)
        self.assertNotIn(exp.objective,html)
        raw=html.split('<script id="trace-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(raw)['experiment']['objective'],exp.objective)

class CredentialTests(unittest.TestCase):
    @patch.dict('os.environ',{},clear=True)
    @patch('jev_swarm.credentials.platform.system',return_value='Darwin')
    @patch('jev_swarm.credentials.subprocess.run')
    def test_only_exact_keychain_service_is_read(self,run,system):
        run.return_value=SimpleNamespace(returncode=0,stdout='sample-token\n')
        self.assertEqual(bedrock_token(),'sample-token')
        self.assertEqual(run.call_args.args[0],['/usr/bin/security','find-generic-password','-s','bedrock-token-acct-a','-w'])

    @patch.dict('os.environ',{'AWS_BEARER_TOKEN_BEDROCK':'environment-token'},clear=True)
    @patch('jev_swarm.credentials.subprocess.run')
    def test_environment_token_does_not_access_keychain(self,run):
        self.assertEqual(bedrock_token(),'environment-token')
        run.assert_not_called()

class ValidationTests(unittest.TestCase):
    def test_probability_validation(self):
        actions=[Action('a','A'),Action('b','B')]
        for probs in ({'a':float('nan'),'b':0},{'a':-1,'b':2},{'a':.2,'b':.2},{'a':True,'b':0},{'a':1}):
            with self.assertRaises(ValueError):Decision('x',probs).validate(actions)
        self.assertAlmostEqual(sum(Decision('x',{'a':.499,'b':.5}).validate(actions).probabilities.values()),1)

    def test_invalid_graph(self):
        spec=deepcopy(SPEC);spec['states'][0]['actions'][0]['to']='missing'
        with self.assertRaises(ValueError):GraphEnvironment(spec)

    def test_invalid_actor_ids(self):
        e=experiment();e.actors[1]=e.actors[0]
        with self.assertRaises(ValueError):e.validate()

    def test_profile_diversity_reproducible(self):
        env=GraphEnvironment(SPEC).describe()
        a=seeded_experiment('Test',8,42,env);b=seeded_experiment('Test',8,42,env)
        self.assertEqual(a,b)
        self.assertGreater(len({json.dumps(x.traits,sort_keys=True) for x in a.actors}),1)

if __name__=='__main__':unittest.main()
