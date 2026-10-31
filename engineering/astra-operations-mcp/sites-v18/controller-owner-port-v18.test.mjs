/** v18 documented GitHub workflow re-run false-completion correction; all tests use synthetic controller port, never a provider. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort as corrected,CONTROLLER_PORT_CONTRACT,causalProofValid} from './controller-owner-port-v18.mjs';
import {delegateThroughOwnerPort as vulnerable} from './controller-owner-port-v17.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000, SHA='a'.repeat(40),RUN=87654321;
const REPO='robert8p/Alpaca-Supabase-Populator',WF='.github/workflows/astra-ingestion-qualification.yml',REF='feat/astra-ingestion-service';
const operation={operation:'github_workflow_dispatch',idempotency_key:'astra-v18-retry-boundary-001',target:{repository:REPO,workflow:WF},params:{ref:REF,inputs:{}}};
const state=({attempt=1,conclusion='success',status='completed'}={})=>{
 const row={state:'CONFIRMED',operation_id:'op-v18-owner-001',change_id:'owner-change-dispatch-001',revision:'rev1',digest:digest(operation),admitted_head_sha:SHA};
 row.dispatch_ack={kind:'github_workflow_dispatch_http_response',source:'controller_captured_github_dispatch_response',status_code:200,api_version:'2026-03-10',workflow_run_id:RUN,operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,repository:REPO,workflow:WF,ref:REF,run_url:`https://api.github.com/repos/${REPO}/actions/runs/${RUN}`,html_url:`https://github.com/${REPO}/actions/runs/${RUN}`};
 row.causal={kind:'workflow_run',operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,run_id:RUN,workflow_id:123,run_attempt:attempt,event:'workflow_dispatch',workflow:WF,ref:REF,repository:REPO,head_sha:SHA,status,conclusion,source:'controller_correlated_github_readback',controller_correlation:row.operation_id};
 return row;
};
function fixture(opts={}){
 const row=state(opts),counts={lookup:0,admit:0,reserve:0,readback:0};
 const port={
  lookupExact:async()=>{counts.lookup++;return opts.historical?{...row}:{state:'absent'};},
  admitExact:async()=>{counts.admit++;return {controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:row.digest,idempotency_key:operation.idempotency_key,operation:operation.operation,scope:'github:actions_write',owner_confirmation:'v18-test-only-confirmation',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'v18-test-only-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:true};},
  reserveAndDispatchUnderOwnerGuard:async()=>{counts.reserve++;return {...row};},
  readbackExact:async()=>{counts.readback++;return {...row};},
 };
 return {row,counts,port};
}
const run=(fn,port)=>fn(operation,port,{clock:()=>EPOCH});

test('v18 contract is distinguished from dormant v17 and cannot assert live integration',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v18'));
test('v17 reproduced defect: manual re-run attempt 2 with original run_id, head SHA, ref can be marked as dispatch success',async()=>{
 const f=fixture({attempt:2});const r=await run(vulnerable,f.port);
 assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);
});
test('v18 blocks same-run-id manual re-run attempt 2 rather than claiming initial dispatch success',async()=>{
 const f=fixture({attempt:2});const r=await run(corrected,f.port);
 assert.equal(r.state,'held');assert.equal(r.code,'causal_proof_missing');assert.equal(r.replay_permitted,false);assert.equal(f.counts.reserve,1);
});
test('v18 also blocks further re-runs despite matching repository/ref/SHA and successful terminal state',async()=>{
 for (const attempt of [3,10,50]) {const f=fixture({attempt});const r=await run(corrected,f.port);assert.equal(r.state,'held');assert.equal(r.replay_permitted,false);}
});
test('v18 first attempt exactly tied to original 200 ACK can still be qualified by caller, synthetic only',async()=>{
 const f=fixture({attempt:1});const r=await run(corrected,f.port);
 assert.equal(r.state,'complete');assert.equal(r.workflow_success_verified,true);assert.deepEqual(f.counts,{lookup:1,admit:1,reserve:1,readback:1});
});
test('v18 historical owner lookup of re-run is readback-only, no new reservation and no replay',async()=>{
 const f=fixture({attempt:2,historical:true});const r=await run(corrected,f.port);
 assert.equal(r.state,'held');assert.equal(r.replay_permitted,false);assert.deepEqual(f.counts,{lookup:1,admit:0,reserve:0,readback:1});
});
test('v18 first attempt with in-progress status is not settlement',async()=>{
 const f=fixture({attempt:1,status:'in_progress',conclusion:null});const r=await run(corrected,f.port);
 assert.equal(r.state,'held');assert.equal(r.replay_permitted,false);
});
test('v18 first attempt with failed outcome is not successful completion',async()=>{
 const f=fixture({attempt:1,conclusion:'failure'});const r=await run(corrected,f.port);
 assert.equal(r.state,'held');assert.equal(r.replay_permitted,false);
});
test('v18 direct causal proof validation rejects re-run, including unchanged original workflow SHA',()=>{
 const f=fixture({attempt:2});assert.equal(causalProofValid(f.row,operation),false);
});
test('v18 rejects malformed/zero run attempt, preserving first-attempt-only proof',()=>{
 for(const attempt of [0,-1,'1',1.5,null]){const f=fixture({attempt});assert.equal(causalProofValid(f.row,operation),false);}
});
