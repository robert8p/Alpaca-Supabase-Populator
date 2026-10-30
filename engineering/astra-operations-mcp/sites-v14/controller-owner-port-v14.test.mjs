/** Synthetic owner-port contract tests ONLY; these cannot establish live owner serialization. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort,causalProofValid,CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v14.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000;
const SERVICE='srv-dbh9fko473hc739an8m0';
const WORKSPACE='tea-d562ma4hg0os73aejnfg';
const REPO='robert8p/Alpaca-Supabase-Populator';
const WORKFLOW='.github/workflows/astra-ingestion-qualification.yml';
const SHA='a'.repeat(40);
const workflow={operation:'github_workflow_dispatch',idempotency_key:'astra-v14-test-workflow-001',target:{repository:REPO,workflow:WORKFLOW},params:{ref:'feat/astra-ingestion-service',inputs:{}}};
const update={operation:'render_update_worker',idempotency_key:'astra-v14-test-worker-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{auto_deploy:false}};
const link={operation:'render_link_environment_group',idempotency_key:'astra-v14-test-group-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{environment_group_id:'evg-abcdefgh'}};
const receipt=x=>({controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:digest(x),idempotency_key:x.idempotency_key,operation:x.operation,scope:x.operation==='github_workflow_dispatch'?'github:actions_write':x.operation==='render_link_environment_group'?'render:env_group_write':'render:services_write',owner_confirmation:'owner-confirmation-example',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'lease-example-owner',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:true});
const row=x=>({state:'CONFIRMED',operation_id:'op-immutable-001',change_id:'owner-change-immutable-001',revision:'rev1',digest:digest(x),...(x.operation==='github_workflow_dispatch'?{admitted_head_sha:SHA}:{})});
const proof=(x,r)=>x.operation==='github_workflow_dispatch'?{kind:'workflow_run',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,run_id:87654321,workflow_id:123,run_attempt:1,event:'workflow_dispatch',workflow:WORKFLOW,ref:workflow.params.ref,repository:REPO,head_sha:SHA,status:'completed',conclusion:'success',source:'controller_correlated_github_readback',controller_correlation:r.operation_id}: {kind:'provider_ack',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,acknowledged:true,source:'controller_captured_provider_response',service_id:SERVICE,workspace_id:WORKSPACE,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed',environment_group_id:x.params.environment_group_id};
function portFor(x,{priorState='absent',modifyIntent=()=>{},modifyReadback=()=>{},modifyReceipt=()=>{},readbackError=false}={}){
 let writes=0,lookups=0,reads=0;
 let intent=row(x);intent.causal=proof(x,intent);modifyIntent(intent);
 const p={
  lookupExact:async()=>{lookups++;return priorState==='absent'?{state:'absent'}:{...intent,state:priorState};},
  admitExact:async()=>{const r=receipt(x);modifyReceipt(r);return r;},
  reserveAndDispatchUnderOwnerGuard:async({hash_version,request_digest})=>{assert.equal(hash_version,'v10-json-v1');assert.equal(request_digest,digest(x));writes++;return {...intent};},
  readbackExact:async()=>{reads++;if(readbackError)throw Error('synthetic lost readback');const rb={...intent};modifyReadback(rb);return rb;},
  get writes(){return writes;},get lookups(){return lookups;},get reads(){return reads;}
 };return p;
}
const run=(x,p)=>delegateThroughOwnerPort(x,p,{clock:()=>EPOCH});

test('v14 remains dormant and refuses to execute without the real owner port',async()=>{
 assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v14');
 const r=await run(workflow,{});assert.equal(r.code,'atomic_owner_port_unbound');assert.equal(r.replay_permitted,false);
});
test('verified synthetic completed workflow succeeds only with all exact causal fields',async()=>{
 const p=portFor(workflow),r=await run(workflow,p);
 assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.equal(p.writes,1);
 assert.equal(r.executed,false);assert.equal(r.replay_permitted,false);
});
test('queued/in-progress GitHub run is NOT completed workflow success',async()=>{
 for(const status of ['queued','in_progress','waiting']){
  const p=portFor(workflow,{modifyIntent:r=>{r.causal.status=status;r.causal.conclusion=null;}}),r=await run(workflow,p);
  assert.equal(r.state,'held',status);assert.equal(r.code,'causal_proof_missing');assert.equal(p.writes,1);
 }
});
test('failed/cancelled workflow is not projected as success',async()=>{
 for(const conclusion of ['failure','cancelled','timed_out','skipped','neutral']){
  const p=portFor(workflow,{modifyIntent:r=>r.causal.conclusion=conclusion});
  assert.equal((await run(workflow,p)).state,'held',conclusion);
 }
});
test('workflow run must match owner-pinned admitted full head SHA',async()=>{
 const p=portFor(workflow,{modifyIntent:r=>{r.causal.head_sha='b'.repeat(40);}});
 assert.equal((await run(workflow,p)).state,'held');
 const q=portFor(workflow,{modifyIntent:r=>{delete r.admitted_head_sha;}});
 assert.equal((await run(workflow,q)).state,'held');
});
test('workflow run must identify exact workflow and attempt, not generic run ID',async()=>{
 for(const field of ['workflow','event','repository','ref','controller_correlation','workflow_id','run_attempt']){
  const p=portFor(workflow,{modifyIntent:r=>{r.causal[field]=field==='workflow_id'||field==='run_attempt'?0:'wrong';}});
  assert.equal((await run(workflow,p)).state,'held',field);
 }
});
test('workflow proof must bind immutable owner change and revision',async()=>{
 const p=portFor(workflow,{modifyIntent:r=>r.causal.revision='rev-another'});
 assert.equal((await run(workflow,p)).state,'held');
 const q=portFor(workflow,{modifyIntent:r=>r.causal.change_id='different-change'});
 assert.equal((await run(workflow,q)).state,'held');
});
test('Render PATCH is accepted configuration-only, not deployed',async()=>{
 const r=await run(update,portFor(update));
 assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);
 assert.equal(r.causal_verified,true);
});
test('Render PATCH without exact config-only response proof remains held',async()=>{
 for(const field of ['auto_deploy_trigger','provider_effect','workspace_id','service_id','source']){
  const p=portFor(update,{modifyIntent:r=>r.causal[field]='wrong'});
  assert.equal((await run(update,p)).state,'held',field);
 }
});
test('environment group link ACK never asserts deployment/secret side-effect completion',async()=>{
 const p=portFor(link);const r=await run(link,p);
 assert.equal(r.state,'held');assert.equal(r.code,'causal_proof_missing');assert.equal(p.writes,1);
 assert.equal((await run(link,portFor(link,{priorState:'CONFIRMED'}))).state,'held');
});
test('new intent identity cannot drift before readback, even with same operation ID',async()=>{
 for(const field of ['change_id','revision']){
  const p=portFor(update,{modifyReadback:r=>{r[field]=field==='revision'?'rev2':'owner-change-another-001';}});
  const r=await run(update,p);
  assert.equal(r.code,'immutable_identity_mismatch_no_retry',field);assert.equal(r.replay_permitted,false);assert.equal(p.writes,1);
 }
});
test('historical exact-key lookup cannot silently change immutable revision on readback',async()=>{
 const p=portFor(workflow,{priorState:'CONFIRMED',modifyReadback:r=>r.revision='rev-new'});
 const r=await run(workflow,p);assert.equal(r.code,'immutable_identity_mismatch_no_retry');assert.equal(p.writes,0);
});
test('owner-pinned SHA changing between intent and readback blocks rather than replay',async()=>{
 const p=portFor(workflow,{modifyReadback:r=>r.admitted_head_sha='b'.repeat(40)});
 const r=await run(workflow,p);assert.equal(r.code,'immutable_identity_mismatch_no_retry');assert.equal(p.writes,1);
});
test('historical confirmed readback never dispatches or consumes new write admission',async()=>{
 const p=portFor(update,{priorState:'CONFIRMED'});const r=await run(update,p);
 assert.equal(r.state,'complete');assert.equal(r.reused,true);assert.equal(p.writes,0);
});
test('readback errors are UNKNOWN and never produce a second provider dispatch',async()=>{
 const p=portFor(update,{readbackError:true});const r=await run(update,p);
 assert.equal(r.code,'readback_unavailable_no_retry');assert.equal(r.replay_permitted,false);assert.equal(p.writes,1);
});
test('owner grant, cost, release and stop gates remain fail-closed before reservation',async()=>{
 for(const [field,bad] of [['grant_verified',false],['zero_cost_verified',false],['release_gate_verified',false],['stop',true]]){
  const p=portFor(update,{modifyReceipt:r=>r[field]=bad});const r=await run(update,p);
  assert.equal(r.state,'blocked',field);assert.equal(p.writes,0);
 }
});
test('source proof function rejects generic audit, desired state and incomplete GitHub run',()=>{
 const r=row(workflow);r.causal=proof(workflow,r);assert.equal(causalProofValid(r,workflow),true);
 r.causal.status='in_progress';assert.equal(causalProofValid(r,workflow),false);
 const u=row(update);u.causal=proof(update,u);assert.equal(causalProofValid(u,update),true);
 u.causal.kind='desired_state';assert.equal(causalProofValid(u,update),false);
});
