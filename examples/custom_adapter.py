"""A stateful software-onboarding adapter; no graph file and no storefront.
Run from the project root: python -m examples.custom_adapter
"""
import asyncio
from copy import deepcopy
import json
from jev_swarm import Action,Actor,DemoPolicy,Experiment,RunConfig,SwarmRunner,export_run

class WorkspaceEnvironment:
    def describe(self):
        return {'adapter':'workspace-setup','version':1}

    async def reset(self,actor,seed):
        return {'project_created':False,'guide_read':False,'task_added':False,'left':False}

    async def observe(self,state,actor):
        return {'screen':'Workspace setup','visible_state':deepcopy(state),
                'instructions':'Create a project, then add your first task. The guide is optional.'}

    async def available_actions(self,state,actor):
        if await self.terminal(state,actor):
            return []
        actions=[Action('leave','End the evaluation',{'tags':['exit']})]
        if not state['guide_read']:
            actions.append(Action('read_guide','Read the setup guide',{'tags':['research']}))
        if not state['project_created']:
            actions.append(Action('create_project','Create a project from a template',{'tags':['speed','commit']}))
        else:
            actions.append(Action('add_task','Add the first task',{'tags':['speed','commit']}))
        return actions

    async def step(self,state,action_id,actor):
        valid={a.id for a in await self.available_actions(state,actor)}
        if action_id not in valid:
            raise ValueError('Illegal action')
        result=deepcopy(state)
        field={'leave':'left','read_guide':'guide_read','create_project':'project_created','add_task':'task_added'}[action_id]
        result[field]=True
        return result

    async def terminal(self,state,actor):
        return 'success' if state['task_added'] else 'exit' if state['left'] else None

async def main():
    experiment=Experiment('Explore workspace setup friction',
        'Pursue your goal using the current observation. Choose only an available action.',[
        Actor('fast','Create a task quickly',{'priority':'speed','patience':.5,'curiosity':.2},'Fast evaluator'),
        Actor('careful','Understand setup before creating a task',{'priority':'research','patience':.9,'curiosity':.9},'Careful evaluator')])
    result=await SwarmRunner(WorkspaceEnvironment(),DemoPolicy()).run(experiment,RunConfig(depth=5,mode='lookahead',beam_width=2))
    export_run(result,'runs/custom-adapter')
    print(json.dumps(result.summary(),indent=2))

if __name__=='__main__':
    asyncio.run(main())
