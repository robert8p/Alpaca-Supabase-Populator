/** v15 synthetic safety regressions only: no live controller/provider connection. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort,CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v15.mjs';
import {digest} from './controller-operations-v10.mjs';
const EPOCH=1793390000,SHA='a'.repeat(40),WORKSPACE='tea-d562ma4hg0os73aejnfg',SERVICE='srv-dbh9fko473hc739an8m0',REPO='robert8p/Alpaca-Supabase-Populator',WORKFLOW='.github/workflows/astra-ingestion-qualification.yml';
const update={operation:'render_update_worker',idempotency_key:'astra-v15-terminal-test-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{auto_deploy:false}};
const workflow={operation:'github_workflow_dispatch',idempotency_key:'astra-v15-workflow-test-001',target:{repository:REPO,workflow:WORKFLOW},params:{ref:'feat/astra-ingestion-service',inputs:{}}};
const row=(x)=>({state:'CONFIRMED',operation_id:'op-immutable-001',change_id:'owner-change-immutable-001',revision:'rev1',digest:digest(x),...(x.operation==='github_workflow_dispatch'?{admitted_head_sha:SHA}:{})});
const proof=(x,r)=>x.operation==='github_workflow_dispatch'?{kind:'workflow_run',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,run_id:87654321,workflow_id:123,run_attempt:1,event:'workflow_dispatch',workflow:WORKFLOW,ref:workflow.params.ref,repository:REPO,head_sha:SHA,status:'completed',conclusion:'success',source:'controller_correlated_github_readback',controller_correlation:r.operation_id}:{kind:'provider_ack',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,acknowledged:true,source:'controller_captured_provider_response',service_id:SERVICE,workspace_id:WORKSPACE,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
function portFor(x,{priorState='absent',intentState='CONFIRMED',readbackState='CONFIRMED',modifyIntent=()=>{},modifyReadback=()=>{}}={}){
  let writes=0,reads=0;const intent=row(x);intent.state=intentState;intent.causal=proof(x,intent);modifyIntent(intent);
  return {
    lookupExact:async()=>priorState==='absent'?{state:'absent'}:{...intent,state:priorState},
    admitExact:async()=>({controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:digest(x),idempotency_key:x.idempotency_key,operation:x.operation,scope:x.operation==='github_workflow_dispatch'?'github:actions_write':'render:services_write',owner_confirmation:'owner-confirmation-example',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'lease-example-owner',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:true}),
    reserveAndDispatchUnderOwnerGuard:async()=>{writes++;return {...intent};},
    readbackExact:async()=>{reads++;const r={...intent,state:readbackState};modifyReadback(r);return r;},
    get writes(){return writes;},get reads(){return reads;}
  };
}
const run=(x,p)=>delegateThroughOwnerPort(x,p,{clock:()=>EPOCH});
test('v15 port remains unbound without controller injection',async()=>{
 assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v15');assert.equal((await run(workflow,{})).code,'atomic_owner_port_unbound');
});
test('historical rejected cannot later become workflow success',async()=>{
 const p=portFor(workflow,{priorState:'REJECTED'});const r=await run(workflow,p);
 assert.equal(r.code,'terminal_owner_state_conflict_no_retry');assert.equal(r.replay_permitted,false);assert.equal(p.writes,0);
});
test('historical confirmed cannot later be reported as rejected',async()=>{
 const p=portFor(update,{priorState:'CONFIRMED',readbackState:'REJECTED'});const r=await run(update,p);
 assert.equal(r.code,'terminal_owner_state_conflict_no_retry');assert.equal(r.replay_permitted,false);assert.equal(p.writes,0);
});
test('UNKNOWN then bare rejected stays held, without proving absence or replaying',async()=>{
 const p=portFor(update,{intentState:'UNKNOWN',readbackState:'REJECTED'});const r=await run(update,p);
 assert.equal(r.state,'held');assert.equal(r.code,'negative_outcome_not_causally_proved');assert.equal(r.replay_permitted,false);assert.equal(p.writes,1);
});
test('DISPATCHING and PREPARED cannot silently become safe rejected',async()=>{
 for(const state of ['DISPATCHING','PREPARED','ACCEPTED']){
  const p=portFor(update,{intentState:state,readbackState:'REJECTED'});const r=await run(update,p);
  assert.equal(r.state,'held',state);assert.equal(r.replay_permitted,false);assert.equal(p.writes,1);
 }
});
test('historical genuine rejected stays rejected without dispatch',async()=>{
 const p=portFor(update,{priorState:'REJECTED',intentState:'REJECTED',readbackState:'REJECTED'});const r=await run(update,p);
 assert.equal(r.state,'rejected');assert.equal(r.replay_permitted,false);assert.equal(p.writes,0);
});
test('late-added workflow SHA cannot fabricate original immutable owner pin',async()=>{
 for(const priorState of ['absent','CONFIRMED']){
  const p=portFor(workflow,{priorState,modifyIntent:r=>{delete r.admitted_head_sha;},modifyReadback:r=>{r.admitted_head_sha=SHA;}});const r=await run(workflow,p);
  assert.equal(r.code,'original_owner_sha_pin_unverified_no_retry',priorState);assert.equal(r.replay_permitted,false);assert.equal(p.writes,priorState==='absent'?1:0);
 }
});
test('invalid original owner SHA pin fails even if later readback adds valid one',async()=>{
 const p=portFor(workflow,{modifyIntent:r=>{r.admitted_head_sha='short';},modifyReadback:r=>{r.admitted_head_sha=SHA;}});const r=await run(workflow,p);
 assert.equal(r.code,'original_owner_sha_pin_unverified_no_retry');assert.equal(r.replay_permitted,false);
});
test('legitimate exact pinned successful workflow is preserved',async()=>{
 const p=portFor(workflow);const r=await run(workflow,p);assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.equal(p.writes,1);
});
test('normal config-only confirmation remains valid, no deployment claim',async()=>{
 const p=portFor(update);const r=await run(update,p);assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);
});