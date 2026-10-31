/** v20: exact original outbound Render PATCH body, source-only/no provider calls. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {delegateThroughOwnerPort as v20,causalProofValid,CONTROLLER_PORT_CONTRACT} from './controller-owner-port-v20.mjs';
import {delegateThroughOwnerPort as v19} from './controller-owner-port-v19.mjs';
import {digest} from './controller-operations-v10.mjs';

const EPOCH=1793390000;
const WORKSPACE='tea-d562ma4hg0os73aejnfg',SERVICE='srv-dbh9fko473hc739an8m0';
const request={operation:'render_update_worker',idempotency_key:'astra-v20-render-patch-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{auto_deploy:false}};
const BODY='{"autoDeployTrigger":"off"}';
const hash=x=>createHash('sha256').update(x,'utf8').digest('hex');
function originalRow(){
 const row={state:'CONFIRMED',operation_id:'op-render-patch-v20',change_id:'owner-render-update-v20',revision:'rev20',digest:digest(request)};
 row.causal={kind:'provider_ack',acknowledged:true,source:'controller_captured_provider_response',operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,service_id:SERVICE,workspace_id:WORKSPACE,auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed'};
 row.patch_ack={kind:'render_service_patch_http_response',source:'controller_captured_render_patch_response',method:'PATCH',status_code:200,path:`/v1/services/${SERVICE}`,operation_id:row.operation_id,change_id:row.change_id,revision:row.revision,digest:row.digest,workspace_id:WORKSPACE,service_id:SERVICE,requested_field:'autoDeployTrigger',requested_value:'off',response_service_id:SERVICE,response_auto_deploy_trigger:'off',provider_effect:'configuration_updated_not_deployed',request_body_capture:'controller_observed_outbound_http_bytes',request_content_type:'application/json',request_body_length:Buffer.byteLength(BODY,'utf8'),request_body_sha256:hash(BODY)};
 return row;
}
function fixture({historical=false,originalModify,readbackModify}={}){
 const base=originalRow(),original=structuredClone(base),readback=structuredClone(base);
 originalModify?.(original);readbackModify?.(readback);
 const counts={lookup:0,admit:0,reserve:0,readback:0};
 const port={
  lookupExact:async()=>{counts.lookup++;return historical?original:{state:'absent'};},
  admitExact:async()=>{counts.admit++;return {controller:'https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5',site:'appgprj_6ae4dcec2034819197d448ca2eea21a3',digest:base.digest,idempotency_key:request.idempotency_key,operation:request.operation,scope:'render:services_write',owner_confirmation:'v20-fixture-no-live-grant',grant_verified:true,zero_cost_verified:true,release_gate_verified:true,stop:false,fence:4,lease:'synthetic-v20-lease',expiry:EPOCH+80,readback_supported:true,workflow_dispatch_enabled:false};},
  reserveAndDispatchUnderOwnerGuard:async()=>{counts.reserve++;return original;},
  readbackExact:async()=>{counts.readback++;return readback;}
 };
 return {original,readback,port,counts};
}
const run=(fn,port,req=request)=>fn(req,port,{clock:()=>EPOCH});
const noRetry=r=>{assert.equal(r.state,'blocked');assert.equal(r.code,'original_render_patch_ack_unverified_no_retry');assert.equal(r.executed,false);assert.equal(r.replay_permitted,false);};

test('v20 contract identifies dormant controller-injected port',()=>assert.equal(CONTROLLER_PORT_CONTRACT,'astra-existing-controller-atomic-v20'));
test('v19 defect reproduced: original PATCH receipt has no evidence of complete outbound body yet claims configuration complete',async()=>{
 const f=fixture({originalModify:r=>{delete r.patch_ack.request_body_capture;delete r.patch_ack.request_content_type;delete r.patch_ack.request_body_length;delete r.patch_ack.request_body_sha256;},readbackModify:r=>{delete r.patch_ack.request_body_capture;delete r.patch_ack.request_content_type;delete r.patch_ack.request_body_length;delete r.patch_ack.request_body_sha256;}});
 const r=await run(v19,f.port);assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);
});
test('v20 refuses the same missing original body provenance and never replays',async()=>{
 const f=fixture({originalModify:r=>{delete r.patch_ack.request_body_capture;delete r.patch_ack.request_content_type;delete r.patch_ack.request_body_length;delete r.patch_ack.request_body_sha256;},readbackModify:r=>{delete r.patch_ack.request_body_capture;delete r.patch_ack.request_content_type;delete r.patch_ack.request_body_length;delete r.patch_ack.request_body_sha256;}});
 noRetry(await run(v20,f.port));assert.equal(f.counts.reserve,1);
});
test('v20 permits bounded EXACT one-field outbound PATCH body; configuration only, never deployed',async()=>{
 const f=fixture();const r=await run(v20,f.port);
 assert.equal(r.state,'complete');assert.equal(r.configuration_only,true);assert.equal(r.deploy_verified,false);
 assert.equal(r.executed,false);assert.equal(r.patch_ack,undefined);assert.equal(r.replay_permitted,false);
 assert.deepEqual(f.counts,{lookup:1,admit:1,reserve:1,readback:1});
});
test('v20 historical original receipt is readback only, never admit/reserve',async()=>{
 const f=fixture({historical:true});const r=await run(v20,f.port);
 assert.equal(r.state,'complete');assert.equal(r.reused,true);assert.deepEqual(f.counts,{lookup:1,admit:0,reserve:0,readback:1});
});
test('v20 fails closed when outbound body includes unapproved branch despite valid PATCH HTTP200',async()=>{
 const broader=JSON.stringify({autoDeployTrigger:'off',branch:'some-other-branch'});
 const f=fixture({originalModify:r=>{r.patch_ack.request_body_sha256=hash(broader);r.patch_ack.request_body_length=Buffer.byteLength(broader);},readbackModify:r=>{r.patch_ack.request_body_sha256=hash(broader);r.patch_ack.request_body_length=Buffer.byteLength(broader);}});
 noRetry(await run(v20,f.port));
});
test('v20 fails closed for additional buildSourceId even with correct returned autoDeployTrigger',async()=>{
 const broader=JSON.stringify({autoDeployTrigger:'off',buildSourceId:'src-foreign'});
 const f=fixture({originalModify:r=>r.patch_ack.request_body_sha256=hash(broader),readbackModify:r=>r.patch_ack.request_body_sha256=hash(broader)});
 noRetry(await run(v20,f.port));
});
test('v20 fails closed for deprecated autoDeploy alias',async()=>{
 const f=fixture({originalModify:r=>r.patch_ack.request_body_sha256=hash('{"autoDeploy":"no"}'),readbackModify:r=>r.patch_ack.request_body_sha256=hash('{"autoDeploy":"no"}')});noRetry(await run(v20,f.port));
});
test('v20 fails closed for wrong autoDeployTrigger payload',async()=>{
 const f=fixture({originalModify:r=>r.patch_ack.request_body_sha256=hash('{"autoDeployTrigger":"commit"}'),readbackModify:r=>r.patch_ack.request_body_sha256=hash('{"autoDeployTrigger":"commit"}')});noRetry(await run(v20,f.port));
});
test('v20 requires exact original byte serialization (not an unbound semantic copy)',async()=>{
 const f=fixture({originalModify:r=>r.patch_ack.request_body_sha256=hash('{ "autoDeployTrigger": "off" }'),readbackModify:r=>r.patch_ack.request_body_sha256=hash('{ "autoDeployTrigger": "off" }')});noRetry(await run(v20,f.port));
});
test('v20 refuses missing or malformed body SHA-256',async()=>{
 for(const value of [undefined,null,'','a'.repeat(64),'not-a-digest']){
  const f=fixture({originalModify:r=>r.patch_ack.request_body_sha256=value,readbackModify:r=>r.patch_ack.request_body_sha256=value});noRetry(await run(v20,f.port));
 }
});
test('v20 refuses unverified original body capture source',async()=>{
 for(const source of [undefined,'client_supplied_expected_payload','render_get_service_response',null]){
  const f=fixture({originalModify:r=>r.patch_ack.request_body_capture=source,readbackModify:r=>r.patch_ack.request_body_capture=source});noRetry(await run(v20,f.port));
 }
});
test('v20 refuses wrong content type in original request',async()=>{
 for(const type of ['text/plain','application/x-www-form-urlencoded',undefined]){
  const f=fixture({originalModify:r=>r.patch_ack.request_content_type=type,readbackModify:r=>r.patch_ack.request_content_type=type});noRetry(await run(v20,f.port));
 }
});
test('v20 refuses body byte length mismatch',async()=>{
 for(const n of [0,1,BODY.length+1,NaN,undefined]){
  const f=fixture({originalModify:r=>r.patch_ack.request_body_length=n,readbackModify:r=>r.patch_ack.request_body_length=n});noRetry(await run(v20,f.port));
 }
});
test('v20 refuses body proof appearing only in later readback',async()=>{
 const f=fixture({originalModify:r=>delete r.patch_ack.request_body_sha256});noRetry(await run(v20,f.port));
});
test('v20 refuses changed body digest between original dispatch and readback',async()=>{
 const f=fixture({readbackModify:r=>r.patch_ack.request_body_sha256=hash('{"autoDeployTrigger":"commit"}')});noRetry(await run(v20,f.port));
});
test('v20 rejects raw outbound JSON body or nested provider response in bounded ack',async()=>{
 const f=fixture({originalModify:r=>r.patch_ack.raw_http_request_body='{"token":"NEVER-ECHO"}',readbackModify:r=>r.patch_ack.raw_http_request_body='{"token":"NEVER-ECHO"}'});
 const r=await run(v20,f.port);noRetry(r);assert.equal(JSON.stringify(r).includes('NEVER-ECHO'),false);
});
test('v20 direct causal validator refuses proof without original outbound body hash',()=>{
 const row=originalRow();assert.equal(causalProofValid(row,request),true);delete row.patch_ack.request_body_sha256;assert.equal(causalProofValid(row,request),false);
});
test('v20 never removes Render environment-group pre-admission gate',async()=>{
 const groupRequest={operation:'render_link_environment_group',idempotency_key:'astra-v20-link-guard-001',target:{workspace_id:WORKSPACE,service_id:SERVICE},params:{environment_group_id:'evg-abcdefgh1234'}};
 let admission=0;const port={lookupExact:async()=>({state:'absent'}),admitExact:async()=>{admission++;throw Error('unexpected');},reserveAndDispatchUnderOwnerGuard:async()=>{admission++;throw Error('unexpected');},readbackExact:async()=>{admission++;throw Error('unexpected');}};
 const r=await run(v20,port,groupRequest);assert.equal(r.code,'environment_group_effect_admission_unimplemented');assert.equal(admission,0);
});
test('v20 cannot bind to a missing real owner port',async()=>{
 const r=await run(v20,null);assert.equal(r.code,'atomic_owner_port_unbound');assert.equal(r.replay_permitted,false);
});