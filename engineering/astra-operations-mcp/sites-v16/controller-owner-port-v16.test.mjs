/** v16 local source-only regressions. No live provider, secrets, owner or runtime. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {delegateThroughOwnerPort as corrected,CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v16.mjs';
import {delegateThroughOwnerPort as priorVersion} from './controller-owner-port-v15.mjs';
import {digest} from './controller-operations-v10.mjs';

const W='tea-d562ma4hg0os73aejnfg',S='srv-dbh9fko473hc739an8m0',EPOCH=1793390000;
const group={operation:'render_link_environment_group',idempotency_key:'astra-v16-envgroup-001',target:{workspace_id:W,service_id:S},params:{environment_group_id:'evg-abcdefgh'}};
const update={operation:'render_update_worker',idempotency_key:'astra-v16-update-001',target:{workspace_id:W,service_id:S},params:{auto_deploy:false}};
const row=x=>({state:'UNKNOWN',operation_id:'op-v16-effect-001',change_id:'owner-change-effect-001',revision:'rev1',digest:digest(x)});
const validAdmission=x=>({controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:digest(x),idempotency_key:x.idempotency_key,operation:x.operation,scope:x.operation==='render_link_environment_group'?'render:env_group_write':'render:services_write',owner_confirmation:'test-only-owner-confirmation',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'test-only-owner-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:false});
function fixture(x,{existing=false,readbackState='UNKNOWN'}={}){
 let lookups=0,admissions=0,reservations=0,readbacks=0;
 const durable=row(x);
 return {
  port:{
   lookupExact:async()=>{lookups++;return existing?{...durable}:{state:'absent'};},
   admitExact:async()=>{admissions++;return validAdmission(x);},
   reserveAndDispatchUnderOwnerGuard:async()=>{reservations++;return {...durable};},
   readbackExact:async()=>{readbacks++;return {...durable,state:readbackState};}
  },
  snapshot:()=>({lookups,admissions,reservations,readbacks})
 };
}
const local={clock:()=>EPOCH};
test('v16 source contract is explicit and not v15',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v16'));
test('v15 regression: a generic grant/admission could reach owner dispatch for an unqualified env-group link',async()=>{
 const f=fixture(group);const r=await priorVersion(group,f.port,local);
 assert.equal(r.state,'held'); assert.equal(f.snapshot().reservations,1);
});
test('v16 refuses new env-group link before admission or any dispatch',async()=>{
 const f=fixture(group);const r=await corrected(group,f.port,local);
 assert.deepEqual(r,{state:'blocked',code:'environment_group_effect_admission_unimplemented',executed:false,replay_permitted:false});
 assert.deepEqual(f.snapshot(),{lookups:1,admissions:0,reservations:0,readbacks:0});
});
test('v16 rejects the same group-link request even if a would-be owner would return generic grant_verified',async()=>{
 const f=fixture(group);const r=await corrected(group,f.port,local);
 assert.equal(r.code,'environment_group_effect_admission_unimplemented');assert.equal(f.snapshot().admissions,0);
});
test('v16 preserves read-only UNKNOWN historical operation reconciliation and never repeats dispatch',async()=>{
 const f=fixture(group,{existing:true});const r=await corrected(group,f.port,local);
 assert.equal(r.state,'held');assert.equal(r.reused,true);assert.equal(r.replay_permitted,false);
 assert.deepEqual(f.snapshot(),{lookups:1,admissions:0,reservations:0,readbacks:1});
});
test('v16 refuses false historical group-link CONFIRMED settlement without deployment causal contract',async()=>{
 const f=fixture(group,{existing:true,readbackState:'CONFIRMED'});const r=await corrected(group,f.port,local);
 assert.equal(r.state,'held');assert.equal(r.code,'causal_proof_missing');assert.equal(f.snapshot().reservations,0);
});
test('v16 does not block a separately qualified Render configuration-only request',async()=>{
 const f=fixture(update);const r=await corrected(update,f.port,local);
 assert.equal(r.state,'held');assert.equal(f.snapshot().reservations,1);
});