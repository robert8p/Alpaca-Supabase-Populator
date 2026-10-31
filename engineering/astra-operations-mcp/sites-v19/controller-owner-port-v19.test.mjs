/** v19 regression: Render PATCH response identity and value, source-only, no provider calls. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort as v19,causalProofValid,CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v19.mjs';
import {delegateThroughOwnerPort as v18} from './controller-owner-port-v18.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000;
const WORKSPACE='tea-d562ma4hg0os73aejnfg', SERVICE='srv-dbh9fko473hc739an8m0';
const request={operation:'render_update_worker',idempotency_key:'astra-v19-render-patch-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{auto_deploy:false}};
function originalRow(){
 const row={state:'CONFIRMED',operation_id:'op-render-patch-001',change_id:'owner-render-update-001',revision:'rev1',digest:digest(request)};
 row.causal={kind:'provider_ack',acknowledged:true,source:'controller_captured_provider_response',operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,service_id:SERVICE,workspace_id:WORKSPACE,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
 row.patch_ack={kind:'render_service_patch_http_response',source:'controller_captured_render_patch_response',method:'PATCH',status_code:200,path:`/v1/services/${SERVICE}`,operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,workspace_id:WORKSPACE,service_id:SERVICE,requested_field:'autoDeployTrigger',requested_value:'off',response_service_id:SERVICE,response_auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
 return row;
}
function fixture({oldAck=false,historical=false,intentModify,rbModify}={}){
 const row=originalRow(), expected=structuredClone(row), rb=structuredClone(row);
 if(oldAck){delete expected.patch_ack;delete rb.patch_ack;}
 intentModify?.(expected);rbModify?.(rb);
 const counts={lookup:0,admit:0,reserve:0,readback:0};
 const port={
  lookupExact:async()=>{counts.lookup++;return historical?expected:{state:'absent'};},
  admitExact:async()=>{counts.admit++;return {controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:row.digest,idempotency_key:request.idempotency_key,operation:'render_update_worker',scope:'render:services_write',owner_confirmation:'v19-synthetic-owner-grant',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'synthetic-owner-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:false};},
  reserveAndDispatchUnderOwnerGuard:async()=>{counts.reserve++;return expected;},
  readbackExact:async()=>{counts.readback++;return rb;},
 };
 return {expected,rb,counts,port};
}
const run=(fn,p)=>fn(request,p,{clock:()=>EPOCH});

test('v19 contract identifies dormant source-only owner port',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v19'));
test('v18 reproduced: a generic service-level provider_ack with no ORIGINAL PATCH result could settle complete',async()=>{
 const f=fixture({oldAck:true});const r=await run(v18,f.port);
 assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(f.counts.reserve,1);
});
test('v19 refuses same generic provider ACK and holds before false positive',async()=>{
 const f=fixture({oldAck:true});const r=await run(v19,f.port);
 assert.equal(r.state,'blocked');assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);assert.equal(f.counts.reserve,1);
});
test('v19 allows configuration-only receipt with original bounded PATCH 200 result, never a deploy claim',async()=>{
 const f=fixture();const r=await run(v19,f.port);
 assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);assert.equal(r.replay_permitted,false);
 assert.equal(r.executed,false);assert.equal(r.patch_ack,undefined);assert.deepEqual(f.counts,{lookup:1,admit:1,reserve:1,readback:1});
});
test('v19 historical exact receipt is readback-only and never re-dispatches',async()=>{
 const f=fixture({historical:true});const r=await run(v19,f.port);
 assert.equal(r.state,'complete');assert.equal(r.reused,true);assert.deepEqual(f.counts,{lookup:1,admit:0,reserve:0,readback:1});
});
test('v19 cannot introduce PATCH proof only during readback',async()=>{
 const f=fixture({intentModify:x=>delete x.patch_ack});const r=await run(v19,f.port);
 assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');assert.equal(r.replay_permitted,false);
});
test('v19 cannot drop PATCH proof during readback',async()=>{
 const f=fixture({rbModify:x=>delete x.patch_ack});const r=await run(v19,f.port);
 assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
});
test('v19 refuses a later GET desired-state observation as PATCH acknowledgement',async()=>{
 const f=fixture({intentModify:x=>x.patch_ack.source='render_get_service_response',rbModify:x=>x.patch_ack.source='render_get_service_response'});const r=await run(v19,f.port);
 assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
});
test('v19 refuses mismatched PATCH HTTP status even when desired field now appears correct',async()=>{
 for(const status of [201,202,204,400,500]){
  const f=fixture({intentModify:x=>x.patch_ack.status_code=status,rbModify:x=>x.patch_ack.status_code=status});
  const r=await run(v19,f.port);assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 }
});
test('v19 rejects original PATCH acknowledgement from another service',async()=>{
 for(const field of ['service_id','response_service_id']){
  const f=fixture({intentModify:x=>x.patch_ack[field]='srv-foreign',rbModify:x=>x.patch_ack[field]='srv-foreign'});
  const r=await run(v19,f.port);assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 }
});
test('v19 rejects HTTP response value inconsistent with requested autoDeployTrigger:off',async()=>{
 for(const value of ['commit','checksPass',null]){
  const f=fixture({intentModify:x=>x.patch_ack.response_auto_deploy_trigger=value,rbModify:x=>x.patch_ack.response_auto_deploy_trigger=value});
  const r=await run(v19,f.port);assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 }
});
test('v19 refuses a misbound immutable change/revision/digest in original PATCH response',async()=>{
 for(const field of ['operation_id','change_id','revision','digest']){
  const f=fixture({intentModify:x=>x.patch_ack[field]='not-original',rbModify:x=>x.patch_ack[field]='not-original'});
  const r=await run(v19,f.port);assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 }
});
test('v19 refuses a changed PATCH acknowledgement between dispatch and readback',async()=>{
 const f=fixture({rbModify:x=>x.patch_ack.requested_value='commit'});const r=await run(v19,f.port);
 assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
});
test('v19 refuses raw provider-response passthrough in original owner receipt',async()=>{
 const f=fixture({intentModify:x=>x.patch_ack.raw_response={envVars:[{value:'no-secret-allowed'}]},rbModify:x=>x.patch_ack.raw_response={envVars:[]}});
 const r=await run(v19,f.port);assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 assert.equal(JSON.stringify(r).includes('no-secret-allowed'),false);
});
test('v19 rejects a POST or GET being mislabeled a PATCH',async()=>{
 for(const method of ['POST','GET','DELETE']){
  const f=fixture({intentModify:x=>x.patch_ack.method=method,rbModify:x=>x.patch_ack.method=method});const r=await run(v19,f.port);
  assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');
 }
});
test('v19 direct causal validator insists on actual original PATCH result summary',()=>{
 const row=originalRow();assert.equal(causalProofValid(row,request),true);
 delete row.patch_ack;assert.equal(causalProofValid(row,request),false);
});
test('v19 still requires original owner pin and first attempt for GitHub dispatch',async()=>{
 const o={operation:'github_workflow_dispatch',idempotency_key:'astra-test-v19-gh-run',target:{repository:'robert8p/Alpaca-Supabase-Populator',workflow:'.github/workflows/astra-ingestion-qualification.yml'},params:{ref:'feat/astra-ingestion-service',inputs:{}}};
 const r=await v19(o,null,{clock:()=>EPOCH});assert.equal(r.code,'atomic_owner_port_unbound');
});
