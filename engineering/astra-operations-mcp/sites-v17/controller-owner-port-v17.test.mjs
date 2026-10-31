/** Source-only v17 regressions: never exercise a provider, controller, secret or credential. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort as corrected,CONTROLLER_PORT_CONTRACT,causalProofValid} from './controller-owner-port-v17.mjs';
import {delegateThroughOwnerPort as vulnerable} from './controller-owner-port-v16.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000, SHA='a'.repeat(40),RUN=87654321,WORKSPACE='tea-d562ma4hg0os73aejnfg',SERVICE='srv-dbh9fko473hc739an8m0',REPO='robert8p/Alpaca-Supabase-Populator',WF='.github/workflows/astra-ingestion-qualification.yml',REF='feat/astra-ingestion-service';
const workflow={operation:'github_workflow_dispatch',idempotency_key:'astra-v17-dispatch-evidence-001',target:{repository:REPO,workflow:WF},params:{ref:REF,inputs:{}}};
const update={operation:'render_update_worker',idempotency_key:'astra-v17-render-config-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{auto_deploy:false}};
const group={operation:'render_link_environment_group',idempotency_key:'astra-v17-render-envgroup-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{environment_group_id:'evg-abcdefgh'}};
const baseRow=x=>({state:'CONFIRMED',operation_id:'op-v17-owner-001',change_id:'owner-change-dispatch-001',revision:'rev1',digest:digest(x),...(x.operation==='github_workflow_dispatch'?{admitted_head_sha:SHA}:{})});
const ack=(r,{id=RUN,version='2026-03-10',status=200}={})=>({kind:'github_workflow_dispatch_http_response',source:'controller_captured_github_dispatch_response',status_code:status,api_version:version,...(version==='2022-11-28'?{return_run_details:true}:{}),workflow_run_id:id,operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,repository:REPO,workflow:WF,ref:REF,run_url:`https://api.github.com/repos/${REPO}/actions/runs/${id}`,html_url:`https://github.com/${REPO}/actions/runs/${id}`});
const proof=(x,r)=>x.operation==='github_workflow_dispatch'?{kind:'workflow_run',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,run_id:RUN,workflow_id:123,run_attempt:1,event:'workflow_dispatch',workflow:WF,ref:REF,repository:REPO,head_sha:SHA,status:'completed',conclusion:'success',source:'controller_correlated_github_readback',controller_correlation:r.operation_id}:{kind:'provider_ack',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,acknowledged:true,source:'controller_captured_provider_response',service_id:SERVICE,workspace_id:WORKSPACE,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
function fixture(x,{existing=false,ackOriginal=true,modifyOriginal=()=>{},modifyReadback=()=>{},readbackState='CONFIRMED'}={}){
 const r=baseRow(x);if(x.operation==='github_workflow_dispatch'&&ackOriginal)r.dispatch_ack=ack(r);r.causal=proof(x,r);modifyOriginal(r);
 let lookups=0,admissions=0,reservations=0,readbacks=0;
 const port={
  lookupExact:async()=>{lookups++;return existing?{...r}:{state:'absent'};},
  admitExact:async()=>{admissions++;return {controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:digest(x),idempotency_key:x.idempotency_key,operation:x.operation,scope:x.operation==='github_workflow_dispatch'?'github:actions_write':x.operation==='render_link_environment_group'?'render:env_group_write':'render:services_write',owner_confirmation:'v17-test-only-owner-confirmation',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'v17-test-only-owner-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:true};},
  reserveAndDispatchUnderOwnerGuard:async()=>{reservations++;return {...r};},
  readbackExact:async()=>{readbacks++;const rb={...r,state:readbackState};modifyReadback(rb);return rb;},
 };
 return {port,counts:()=>({lookups,admissions,reservations,readbacks})};
}
const run=(func,x,port)=>func(x,port,{clock:()=>EPOCH});

test('v17 contract distinguishes source-only corrected delegation',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v17'));
test('real documented v16 false-completion: correlated but unbound run is accepted without captured POST run id',async()=>{
 const f=fixture(workflow,{ackOriginal:false}); const r=await run(vulnerable,workflow,f.port);
 assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.equal(f.counts().reservations,1);
});
test('v17 refuses to claim completed workflow without original durable dispatch HTTP 200 run id',async()=>{
 const f=fixture(workflow,{ackOriginal:false});const r=await run(corrected,workflow,f.port);
 assert.equal(r.state,'blocked');assert.equal(r.code,'original_dispatch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);assert.equal(f.counts().reservations,1);
});
test('v17 refuses run metadata inserted only at later readback, no replay',async()=>{
 const f=fixture(workflow,{ackOriginal:false,modifyReadback:rb=>{rb.dispatch_ack=ack(rb);}}); const r=await run(corrected,workflow,f.port);
 assert.equal(r.code,'original_dispatch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);
});
test('v17 exact owner-captured HTTP 200 response and terminal correlated run may be complete (synthetic only)',async()=>{
 const f=fixture(workflow);const r=await run(corrected,workflow,f.port);
 assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.equal(r.replay_permitted,false);assert.deepEqual(f.counts(),{lookups:1,admissions:1,reservations:1,readbacks:1});
});
test('v17 historical lookup with exact durable POST run binding is readback only',async()=>{
 const f=fixture(workflow,{existing:true});const r=await run(corrected,workflow,f.port);
 assert.equal(r.state,'complete');assert.equal(r.reused,true);assert.deepEqual(f.counts(),{lookups:1,admissions:0,reservations:0,readbacks:1});
});
test('v17 supports GitHub 2022-11-28 opt-in run details only when explicitly recorded',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack=ack(r,{version:'2022-11-28'});}});
 assert.equal((await run(corrected,workflow,f.port)).state,'complete');
});
test('v17 refuses 2022-11-28 without return_run_details:true',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack=ack(r,{version:'2022-11-28'});delete r.dispatch_ack.return_run_details;}});
 assert.equal((await run(corrected,workflow,f.port)).code,'original_dispatch_ack_unverified_no_retry');
});
test('v17 HTTP 204 without response binding remains unverified, never creates run ID',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack=ack(r,{status:204});}});const result=await run(corrected,workflow,f.port);
 assert.equal(result.code,'original_dispatch_ack_unverified_no_retry');assert.equal(result.replay_permitted,false);
});
test('v17 rejects readback swapping another dispatch run ID',async()=>{
 const f=fixture(workflow,{modifyReadback:rb=>{rb.dispatch_ack=ack(rb,{id:RUN+1});}});const r=await run(corrected,workflow,f.port);
 assert.equal(r.code,'original_dispatch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);
});
test('v17 refuses falsely correlated successful run ID differing from owner-captured dispatch run',async()=>{
 const f=fixture(workflow,{modifyReadback:rb=>{rb.causal={...rb.causal,run_id:RUN+1};}});const r=await run(corrected,workflow,f.port);
 assert.equal(r.state,'held');assert.equal(r.code,'causal_proof_missing');assert.equal(r.replay_permitted,false);
});
test('v17 rejects dispatch ACK URLs pointing outside exact repository/run identity',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack={...r.dispatch_ack,html_url:'https://github.com/other/repo/actions/runs/'+RUN};}});
 assert.equal((await run(corrected,workflow,f.port)).code,'original_dispatch_ack_unverified_no_retry');
});
test('v17 rejects ACK with run id exceeding exact JavaScript safe integer range',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack=ack(r,{id:9007199254740992});}});
 assert.equal((await run(corrected,workflow,f.port)).code,'original_dispatch_ack_unverified_no_retry');
});
test('v17 refuses forged ACK that is not bound to immutable original change ID/revision',async()=>{
 const f=fixture(workflow,{modifyOriginal:r=>{r.dispatch_ack={...r.dispatch_ack,change_id:'owner-change-fake-001'};}});
 assert.equal((await run(corrected,workflow,f.port)).code,'original_dispatch_ack_unverified_no_retry');
});
test('v17 does not weaken v16 new environment-group secret/deploy pre-admission block',async()=>{
 const f=fixture(group);const r=await run(corrected,group,f.port);
 assert.equal(r.code,'environment_group_effect_admission_unimplemented');assert.deepEqual(f.counts(),{lookups:1,admissions:0,reservations:0,readbacks:0});
});
test('v17 leaves Render PATCH configuration-only settlement unchanged',async()=>{
 const f=fixture(update);const r=await run(corrected,update,f.port);
 assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);
});
test('v17 blocked unknown HTTP acceptance can still be read back historically without resubmission',async()=>{
 const f=fixture(workflow,{existing:true,ackOriginal:false,readbackState:'UNKNOWN'});const r=await run(corrected,workflow,f.port);
 assert.equal(r.code,'original_dispatch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);assert.equal(f.counts().reservations,0);
});
