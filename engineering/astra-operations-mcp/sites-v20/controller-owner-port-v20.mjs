/**
 * v20 Render service PATCH outbound HTTP request-body confinement guard, retaining v17 response-to-run binding and v16 environment-group correction of the source-only controller-owned port. NOT a provider adapter or executor.
 * The port MUST be injected by the existing application controller, never by MCP input.
 * No admission/permission claim follows from successful synthetic tests.
 */
import {validate, validateReceipt, digest, safeOperationId} from './controller-operations-v10.mjs';
import {createHash} from 'node:crypto';

export const CONTROLLER_PORT_CONTRACT='astra-existing-controller-atomic-v20';
// The one approved Render PATCH body is an exact UTF-8 JSON document.
// The controller MUST hash the bytes actually handed to the HTTP transport,
// not the expected plan, a later service GET, or any caller assertion.
const APPROVED_PATCH_BODY='{"autoDeployTrigger":"off"}';
const APPROVED_PATCH_BODY_SHA256=createHash('sha256').update(APPROVED_PATCH_BODY,'utf8').digest('hex');
const APPROVED_PATCH_BODY_BYTES=Buffer.byteLength(APPROVED_PATCH_BODY,'utf8');
const required=['lookupExact','admitExact','reserveAndDispatchUnderOwnerGuard','readbackExact'];
const blocked=code=>({state:'blocked',code,executed:false,replay_permitted:false});
const isObject=x=>x!==null&&typeof x==='object'&&!Array.isArray(x)&&Object.getPrototypeOf(x)===Object.prototype;
const isRevision=x=>typeof x==='string'&&x.length>=1&&x.length<=72&&/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(x);
const isChangeId=x=>typeof x==='string'&&x.length>=12&&x.length<=96&&/^[a-zA-Z0-9][a-zA-Z0-9._:-]*$/.test(x);
const clockAt=clock=>{const t=clock();return typeof t==='number'&&Number.isFinite(t)&&t>=0?t:null;};
const freezeCopy=x=>{
 const c=structuredClone(x);
 function freeze(v){if(v&&typeof v==='object'){for(const part of Object.values(v))freeze(part);Object.freeze(v);}return v;}
 return freeze(c);
};
const safeRow=(r,hash)=>isObject(r)&&r.digest===hash&&safeOperationId(r.operation_id)&&isChangeId(r.change_id)&&isRevision(r.revision)&&['PREPARED','DISPATCHING','UNKNOWN','ACCEPTED','CONFIRMED','REJECTED'].includes(r.state);

/**
 * GitHub's 2026-03-10 workflow_dispatch response returns workflow_run_id,
 * run_url and html_url (HTTP 200). Older 2022-11-28 requests require the
 * explicit return_run_details flag. HTTP 204, a missing response after a
 * timeout, or a run found by time/ref alone is not an exact dispatch receipt.
 * This must be OWNER-captured and durably bound to the original change;
 * the MCP caller is never trusted to supply an acknowledgement.
 */
const dispatchAckValid=(row,request)=>{
 const a=row?.dispatch_ack;
 if(!isObject(a)||a.kind!=='github_workflow_dispatch_http_response'||
    a.source!=='controller_captured_github_dispatch_response'||a.status_code!==200||
    !((a.api_version==='2026-03-10'&&a.return_run_details===undefined)||
      (a.api_version==='2022-11-28'&&a.return_run_details===true))||
    !Number.isSafeInteger(a.workflow_run_id)||a.workflow_run_id<1||
    a.operation_id!==row.operation_id||a.change_id!==row.change_id||
    a.revision!==row.revision||a.digest!==row.digest||
    a.repository!==request.target.repository||a.workflow!==request.target.workflow||
    a.ref!==request.params.ref)return false;
 const prefix=`https://api.github.com/repos/${request.target.repository}/actions/runs/${a.workflow_run_id}`;
 const html=`https://github.com/${request.target.repository}/actions/runs/${a.workflow_run_id}`;
 return a.run_url===prefix&&a.html_url===html;
};
const sameDispatchAck=(a,b)=>isObject(a)&&isObject(b)&&
 ['kind','source','status_code','api_version','return_run_details','workflow_run_id',
  'operation_id','change_id','revision','digest','repository','workflow','ref',
  'run_url','html_url'].every(key=>a[key]===b[key]);


/**
 * Render's PATCH /v1/services/{serviceId} returns HTTP 200 with the updated
 * service object, including id and autoDeployTrigger (Render official API).
 * It does NOT deploy. A later GET showing the desired setting is NOT causal
 * evidence that this exact approved PATCH took effect. Never copy the full
 * service response or its nested fields into the MCP receipt.
 *
 * This bounded projection MUST be captured by the controller directly from
 * its ORIGINAL guarded PATCH HTTP response AND the exact transmitted PATCH
 * request body digest/length, persisted with its immutable operation. It is not accepted from caller input or a later GET. The real
 * owner port still has to prove those capture/serialization guarantees.
 */
const renderPatchAckValid=(row,request)=>{
 const a=row?.patch_ack;
 return isObject(a)&&
   a.kind==='render_service_patch_http_response'&&
   a.source==='controller_captured_render_patch_response'&&
   a.method==='PATCH'&&a.status_code===200&&
   a.path===`/v1/services/${request.target.service_id}`&&
   a.operation_id===row.operation_id&&a.change_id===row.change_id&&
   a.revision===row.revision&&a.digest===row.digest&&
   a.workspace_id===request.target.workspace_id&&
   a.service_id===request.target.service_id&&
   a.requested_field==='autoDeployTrigger'&&a.requested_value==='off'&&
   a.response_service_id===request.target.service_id&&
   a.response_auto_deploy_trigger==='off'&&
   a.provider_effect==='configuration_updated_not_deployed'&&
   // PATCH also permits branch, build source and startup configuration changes.
   // Naming only the approved field cannot prove absence of extra effects.
   a.request_body_capture==='controller_observed_outbound_http_bytes'&&
   a.request_content_type==='application/json'&&
   a.request_body_length===APPROVED_PATCH_BODY_BYTES&&
   a.request_body_sha256===APPROVED_PATCH_BODY_SHA256&&
   // Reject permissive raw provider-response passthroughs. A complete
   // service object may contain unrelated configuration and secrets.
   Object.keys(a).every(k=>[
     'kind','source','method','status_code','path','operation_id',
     'change_id','revision','digest','workspace_id','service_id',
     'requested_field','requested_value','response_service_id',
     'response_auto_deploy_trigger','provider_effect',
     'request_body_capture','request_content_type',
     'request_body_length','request_body_sha256'
   ].includes(k));
};
const sameRenderPatchAck=(a,b)=>isObject(a)&&isObject(b)&&
 ['kind','source','method','status_code','path','operation_id',
  'change_id','revision','digest','workspace_id','service_id',
  'requested_field','requested_value','response_service_id',
  'response_auto_deploy_trigger','provider_effect',
  'request_body_capture','request_content_type',
  'request_body_length','request_body_sha256'].every(k=>a[k]===b[k]);

/**
 * Only controller-owned *causal* evidence may qualify a completed state;
 * desired configuration, elapsed time and standalone provider status do not.
 */
/**
 * A controller's immutable row and its causal proof must refer to the *same*
 * operation, revision and change. Never use mere provider desired state, a
 * GitHub run ID, a Render config PATCH, or a partially completed workflow to
 * infer completed side effects. Requires owner-verified causal fields, NOT
 * caller-supplied permissions. Historical v11 receipts are not upgraded.
 *
 * Real integration stays blocked until the ingestion controller implements
 * this contract and proves owner-atomic reservation and readback. These checks
 * are necessary, not sufficient, to establish production provenance.
 */
export function causalProofValid(row,request){
 if(!safeRow(row,digest(request)))return false;
 const c=row.causal;
 if(!isObject(c)||c.operation_id!==row.operation_id||c.digest!==row.digest||
    c.change_id!==row.change_id||c.revision!==row.revision)return false;
 if(request.operation==='render_update_worker')return renderPatchAckValid(row,request)&&
   c.kind==='provider_ack'&&c.acknowledged===true&&
   c.source==='controller_captured_provider_response'&&
   c.service_id===request.target.service_id&&c.workspace_id===request.target.workspace_id&&
   c.auto_deploy_trigger==='off'&&c.provider_effect==='configuration_updated_not_deployed';
 // Render environment-group linking inherits secrets AND triggers a deploy.
 // The link API acknowledgement carries no uniquely correlated deploy result.
 // Hold the result until a separately designed real owner-side linkage+deploy
 // settlement port passes acceptance. No synthetic "deploy succeeded" flag.
 if(request.operation==='render_link_environment_group')return false;
 if(request.operation==='github_workflow_dispatch')return c.kind==='workflow_run'&&
   Number.isSafeInteger(c.run_id)&&c.run_id>0&&
   Number.isSafeInteger(c.workflow_id)&&c.workflow_id>0&&
   // GitHub retains run_id, GITHUB_SHA and GITHUB_REF across manual re-runs,
   // incrementing run_attempt. A subsequent attempt's success is NOT proof
   // that the first execution caused by our exact dispatch succeeded.
   // Require the original attempt; further attempts need a separate
   // controller-owned, explicitly approved reconciliation contract.
   c.run_attempt===1&&
   c.event==='workflow_dispatch'&&c.workflow===request.target.workflow&&
   c.ref===request.params.ref&&c.repository===request.target.repository&&
   typeof row.admitted_head_sha==='string'&&/^[0-9a-f]{40}$/.test(row.admitted_head_sha)&&
   c.head_sha===row.admitted_head_sha&&
   dispatchAckValid(row,request)&&
   c.run_id===row.dispatch_ack.workflow_run_id&&
   c.status==='completed'&&c.conclusion==='success'&&
   c.source==='controller_correlated_github_readback'&&
   c.controller_correlation===row.operation_id;
 return false;
}
/**
 * This helper cannot itself prove a real port serializes stop/fence or persists reservations.
 * Those are independent owner-side acceptance criteria. It never resubmits an unknown intent.
 */
export async function delegateThroughOwnerPort(x,port,{clock=()=>Date.now()/1000}={}){
 const invalid=validate(x);if(invalid)return blocked(invalid);
 // Render does not offer a Free background-worker plan. V10's candidate worker
 // has plan:'free' and cannot satisfy a genuine zero-incremental-cost admission.
 // Keep creation in backlog for a separately reviewed, correctly priced spec;
 // do not silently substitute a paid plan or duplicate the existing worker.
 if(x.operation==='render_create_worker')return blocked('worker_creation_plan_and_cost_unqualified');
 if(!port||required.some(k=>typeof port[k]!=='function'))return blocked('atomic_owner_port_unbound');
 if(typeof clock!=='function'||clockAt(clock)===null)return blocked('invalid_clock');
 const request=freezeCopy(x),hash=digest(request);
 let prior;
 try{prior=await port.lookupExact({idempotency_key:request.idempotency_key,request_digest:hash});}
 catch{return blocked('exact_lookup_unavailable');}
 if(!isObject(prior)||prior.state===undefined)return blocked('exact_lookup_unverified');
 if(prior.state!=='absent'){
  if(!safeRow(prior,hash))return blocked('idempotency_conflict_or_unverified');
  // Pure historical readback: never dispatch the same (or changed) intent again.
  return await projectReadback(request,port,prior.operation_id,hash,true,prior);
 }
 // Material v15 defect: a generic grant_verified receipt could admit a NEW
 // Render environment-group link despite no owner-verified inventory of its
 // inherited env values / secret files, variable collision handling, or the
 // automatic deployment it triggers. Merely holding readback AFTER dispatch
 // does not prevent those irreversible side effects.
 //
 // The existing four-method controller port has no such immutable effect
 // admission. Fail closed BEFORE admit/reserve/dispatch. Historical exact-key
 // readback remains available above. This capability stays on the deferred
 // owner backlog; lift this gate ONLY after a real controller-owned contract
 // binds immutable group/service effect evidence, explicit secret/deploy
 // authority, physical resource lock, and causal deployment settlement.
 if(request.operation==='render_link_environment_group')
  return blocked('environment_group_effect_admission_unimplemented');
 let receipt;
 try{receipt=await port.admitExact({request,request_digest:hash});}
 catch{return blocked('owner_admission_unavailable');}
 const checkedAt=clockAt(clock);
 if(checkedAt===null)return blocked('invalid_clock');
 const admissionError=validateReceipt(receipt,request,checkedAt);
 if(admissionError)return blocked(admissionError);
 // Even this is only a preflight; the REAL owner port must atomically revalidate
 // stop, current fence, lease, expiry and action-time grant before provider dispatch.
 const immediatelyBefore=clockAt(clock);
 if(immediatelyBefore===null||immediatelyBefore>=receipt.expiry)return blocked('stale_or_no_readback');
 let intent;
 try{
  intent=await port.reserveAndDispatchUnderOwnerGuard({request,request_digest:hash,admission:receipt,hash_version:'v10-json-v1'});
 }catch{return blocked('uncertain_owner_dispatch_no_retry');}
 if(!safeRow(intent,hash))return blocked('unverified_owner_dispatch_no_retry');
 return await projectReadback(request,port,intent.operation_id,hash,false,intent);
}
async function projectReadback(request,port,operationId,hash,reused,expected){
 let rb;
 try{rb=await port.readbackExact({idempotency_key:request.idempotency_key,operation_id:operationId,request_digest:hash});}
 catch{return blocked('readback_unavailable_no_retry');}
 if(!safeRow(rb,hash)||rb.operation_id!==operationId)return blocked('readback_unverified_no_retry');
 // Render PATCH must be bound to the ORIGINAL controller-owned HTTP 200
 // response, including exact service ID and autoDeployTrigger:off. A later
 // service GET showing the desired state cannot prove this guarded PATCH.
 // Missing or conflicting acknowledgements are uncertain; NEVER retry.
 if(request.operation==='render_update_worker'&&
    (!renderPatchAckValid(expected,request)||!renderPatchAckValid(rb,request)||
     !sameRenderPatchAck(expected.patch_ack,rb.patch_ack)))
    return blocked('original_render_patch_ack_unverified_no_retry');
 // A pinned GitHub head SHA must exist in the ORIGINAL controller reservation or
 // historical exact-key lookup, not first appear in a later readback. Otherwise
 // a late-attested SHA could turn an unpinned workflow into apparent success.
 if(request.operation==='github_workflow_dispatch'&&
    (typeof expected.admitted_head_sha!=='string'||!/^[0-9a-f]{40}$/.test(expected.admitted_head_sha)))
    return blocked('original_owner_sha_pin_unverified_no_retry');
 // The controller's original durable dispatch result MUST carry the actual
 // GitHub POST response's workflow_run_id. It cannot appear only in later
 // readback; that could correlate an unrelated successful workflow run from
 // the same branch/ref/SHA. 204 and lost-response outcomes remain held, never
 // trigger a second POST. Validate both observations against exact request.
 if(request.operation==='github_workflow_dispatch'&&
    (!dispatchAckValid(expected,request)||!dispatchAckValid(rb,request)||
     !sameDispatchAck(expected.dispatch_ack,rb.dispatch_ack)))
    return blocked('original_dispatch_ack_unverified_no_retry');
 if(rb.change_id!==expected.change_id||rb.revision!==expected.revision||
    (expected.admitted_head_sha!==undefined&&rb.admitted_head_sha!==expected.admitted_head_sha))
    return blocked('immutable_identity_mismatch_no_retry');
 // Final outcomes are immutable: a previously CONFIRMED or REJECTED receipt
 // changing its state between owner lookup/reservation and readback is a
 // consistency failure, NOT permission to reclassify the old operation.
 if((expected.state==='CONFIRMED'||expected.state==='REJECTED')&&rb.state!==expected.state)
    return blocked('terminal_owner_state_conflict_no_retry');
 const safe={operation_id:operationId,change_id:rb.change_id,revision:rb.revision,executed:false,reused,replay_permitted:false};
 if(rb.state==='CONFIRMED'&&causalProofValid(rb,request))
   return {...safe,state:'complete',causal_verified:true,
     ...(request.operation==='render_update_worker'?{deploy_verified:false,configuration_only:true}:{}),
     ...(request.operation==='github_workflow_dispatch'?{workflow_success_verified:true}:{})};
 // UNKNOWN, PREPARED, DISPATCHING and ACCEPTED are not proof of *no* provider
 // effect. A later REJECTED label cannot clear their uncertainty without an
 // owner-designed, causally verified negative-outcome contract. No replay.
 if(rb.state==='REJECTED'&&expected.state!=='REJECTED')
    return {...safe,state:'held',code:'negative_outcome_not_causally_proved',causal_verified:false};
 if(rb.state==='REJECTED')return {...safe,state:'rejected',causal_verified:false};
 // PREPARED or DISPATCHING also cannot settle while the executor may still send.
 // CONFIRMED without a matching causal acknowledgement is conservatively held.
 return {...safe,state:'held',code:rb.state==='CONFIRMED'?'causal_proof_missing':'owner_operation_not_causally_settled',causal_verified:false};
}