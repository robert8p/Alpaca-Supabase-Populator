/** v21: regression qualification of IMMUTABLE original terminal causal evidence.
 * Synthetic controller-shaped fixtures only; no production owner port/provider calls.
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {delegateThroughOwnerPort as corrected, CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v21.mjs';
import {delegateThroughOwnerPort as vulnerable} from './controller-owner-port-v20.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000;
const WS='tea-d562ma4hg0os73aejnfg', SERVICE='srv-dbh9fko473hc739an8m0';
const REPO='robert8p/Alpaca-Supabase-Populator', WF='.github/workflows/astra-ingestion-qualification.yml', REF='feat/astra-ingestion-service';
const PATCH_BODY='{"autoDeployTrigger":"off"}';
const SHA='a'.repeat(40),RUN=87654321;
const renderReq={operation:'render_update_worker',idempotency_key:'astra-v21-terminal-proof-render-01',target:{workspace_id:WS,service_id:SERVICE},params:{auto_deploy:false}};
const githubReq={operation:'github_workflow_dispatch',idempotency_key:'astra-v21-terminal-proof-github-01',target:{repository:REPO,workflow:WF},params:{ref:REF,inputs:{}}};
const clone=x=>structuredClone(x);
function row(req){
 const r={state:'CONFIRMED',operation_id:'op-v21-terminal-proof',change_id:'owner-change-terminal-v21',revision:'rev21',digest:digest(req)};
 if(req.operation==='render_update_worker'){
  r.causal={kind:'provider_ack',acknowledged:true,source:'controller_captured_provider_response',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,service_id:SERVICE,workspace_id:WS,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
  r.patch_ack={kind:'render_service_patch_http_response',source:'controller_captured_render_patch_response',method:'PATCH',status_code:200,path:`/v1/services/${SERVICE}`,operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,workspace_id:WS,service_id:SERVICE,requested_field:'autoDeployTrigger',requested_value:'off',response_service_id:SERVICE,response_auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed',request_body_capture:'controller_observed_outbound_http_bytes',request_content_type:'application/json',request_body_length:Buffer.byteLength(PATCH_BODY),request_body_sha256:createHash('sha256').update(PATCH_BODY).digest('hex')};
 }else{
  r.admitted_head_sha=SHA;
  r.dispatch_ack={kind:'github_workflow_dispatch_http_response',source:'controller_captured_github_dispatch_response',status_code:200,api_version:'2026-03-10',workflow_run_id:RUN,operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,repository:REPO,workflow:WF,ref:REF,run_url:`https://api.github.com/repos/${REPO}/actions/runs/${RUN}`,html_url:`https://github.com/${REPO}/actions/runs/${RUN}`};
  r.causal={kind:'workflow_run',operation_id:r.operation_id,change_id:r.change_id,revision:r.revision,digest:r.digest,run_id:RUN,workflow_id:123,run_attempt:1,event:'workflow_dispatch',workflow:WF,ref:REF,repository:REPO,head_sha:SHA,status:'completed',conclusion:'success',source:'controller_correlated_github_readback',controller_correlation:r.operation_id};
 }
 return r;
}
function scenario(req,{historical=true,mutateOriginal=()=>{},mutateReadback=()=>{}}={}){
 const original=row(req),readback=row(req);
 mutateOriginal(original);mutateReadback(readback);
 const counts={lookup:0,admit:0,reserve:0,readback:0};
 const port={
  lookupExact:async()=>{counts.lookup++;return historical?clone(original):{state:'absent'};},
  admitExact:async()=>{counts.admit++;return {controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:digest(req),idempotency_key:req.idempotency_key,operation:req.operation,scope:req.operation==='render_update_worker'?'render:services_write':'github:actions_write',owner_confirmation:'synthetic-v21-only-not-live-grant',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'synthetic-v21-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:req.operation==='github_workflow_dispatch'};},
  reserveAndDispatchUnderOwnerGuard:async()=>{counts.reserve++;return clone(original);},
  readbackExact:async()=>{counts.readback++;return clone(readback);}
 };
 return {port,counts,original,readback};
}
const run=(fn,req,f)=>fn(req,f.port,{clock:()=>EPOCH});
const failClosed=(r)=>{assert.equal(r.state,'blocked');assert.equal(r.code,'original_terminal_causal_proof_unverified_no_retry');assert.equal(r.executed,false);assert.equal(r.replay_permitted,false);};

test('v21 contract is new but still only a dormant controller-injected caller',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v21'));
test('NEW verified v20 source defect: Render original CONFIRMED based on unrelated GET is later upgraded to complete',async()=>{
 const f=scenario(renderReq,{mutateOriginal:r=>r.causal.source='uncorrelated_later_service_get'});
 const r=await run(vulnerable,renderReq,f);assert.equal(r.state,'complete');assert.equal(r.causal_verified,true);assert.equal(f.counts.reserve,0);
});
test('v21 blocks the same invalid original Render terminal causal proof without replay',async()=>{
 const f=scenario(renderReq,{mutateOriginal:r=>r.causal.source='uncorrelated_later_service_get'});
 failClosed(await run(corrected,renderReq,f));assert.equal(f.counts.reserve,0);
});
test('v21 blocks original terminal Render outcome with no causal object',async()=>{
 const f=scenario(renderReq,{mutateOriginal:r=>delete r.causal});failClosed(await run(corrected,renderReq,f));
});
test('v21 blocks original terminal Render outcome with failed provider acknowledgement',async()=>{
 const f=scenario(renderReq,{mutateOriginal:r=>r.causal.acknowledged=false});failClosed(await run(corrected,renderReq,f));
});
test('v21 also prevents new-dispatch-path original terminal Render retroactive proof',async()=>{
 const f=scenario(renderReq,{historical:false,mutateOriginal:r=>r.causal.source='GET_service_status_not_causal'});
 failClosed(await run(corrected,renderReq,f));assert.equal(f.counts.reserve,1);
});
test('v21 continues to accept original and readback CONFIRMED Render with matching causality, config only',async()=>{
 const f=scenario(renderReq);const r=await run(corrected,renderReq,f);assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);
});
test('v21 permits legitimate Render ACCEPTED->CONFIRMED causal settlement with original PATCH proof',async()=>{
 const f=scenario(renderReq,{mutateOriginal:r=>{r.state='ACCEPTED';delete r.causal;}});
 const r=await run(corrected,renderReq,f);assert.equal(r.state,'complete');assert.equal(r.causal_verified,true);assert.equal(f.counts.reserve,0);
});
test('NEW verified v20 source defect: original terminal GitHub attempt 2 can be upgraded by later readback of attempt 1',async()=>{
 const f=scenario(githubReq,{mutateOriginal:r=>r.causal.run_attempt=2});
 const r=await run(vulnerable,githubReq,f);assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);
});
test('v21 blocks GitHub terminal attempt drift without replay',async()=>{
 const f=scenario(githubReq,{mutateOriginal:r=>r.causal.run_attempt=2});failClosed(await run(corrected,githubReq,f));assert.equal(f.counts.reserve,0);
});
test('v21 blocks originally absent terminal GitHub causal proof',async()=>{
 const f=scenario(githubReq,{mutateOriginal:r=>delete r.causal});failClosed(await run(corrected,githubReq,f));
});
test('v21 blocks original terminal GitHub failure later rewritten as success',async()=>{
 const f=scenario(githubReq,{mutateOriginal:r=>r.causal.conclusion='failure'});failClosed(await run(corrected,githubReq,f));
});
test('v21 accepts first attempt original and readback valid GitHub terminal success',async()=>{
 const f=scenario(githubReq);const r=await run(corrected,githubReq,f);assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);
});
test('v21 accepts legitimate GitHub DISPATCHING->CONFIRMED verified original POST + terminal first attempt',async()=>{
 const f=scenario(githubReq,{mutateOriginal:r=>{r.state='DISPATCHING';delete r.causal;}});
 const r=await run(corrected,githubReq,f);assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.equal(f.counts.reserve,0);
});
test('v21 does not lift environment-group pre-admission secret/deploy hold',async()=>{
 const request={operation:'render_link_environment_group',idempotency_key:'astra-v21-env-group-guard',target:{workspace_id:WS,service_id:SERVICE},params:{environment_group_id:'evg-abcdefgh1234'}};
 const counts={admit:0,reserve:0};const port={lookupExact:async()=>({state:'absent'}),admitExact:async()=>{counts.admit++;throw Error('unexpected');},reserveAndDispatchUnderOwnerGuard:async()=>{counts.reserve++;throw Error('unexpected');},readbackExact:async()=>{throw Error('unexpected');}};
 const r=await corrected(request,port,{clock:()=>EPOCH});assert.equal(r.code,'environment_group_effect_admission_unimplemented');assert.deepEqual(counts,{admit:0,reserve:0});
});