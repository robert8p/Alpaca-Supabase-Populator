/** Controller-owned, fail-closed missing-operation delegation. Never a provider client. */
import {createHash} from 'node:crypto';
const WORKSPACE='tea-d562ma4hg0os73aejnfg',REPO='robert8p/Alpaca-Supabase-Populator';
const CONTROLLER='https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5';
const SITE='appgprj_6ae4dcec2034819197d448ca2eea21a3';
const OPS={render_create_worker:'render:services_write',render_update_worker:'render:services_write',render_link_environment_group:'render:env_group_write',github_workflow_dispatch:'github:actions_write'};
const plain=x=>x!==null&&typeof x==='object'&&!Array.isArray(x)&&Object.getPrototypeOf(x)===Object.prototype;
const exact=(x,keys)=>plain(x)&&Object.keys(x).every(k=>keys.includes(k));
const blocked=code=>({state:'blocked',code,executed:false});
/** Only bounded opaque controller-generated IDs can be reflected to an MCP caller. */
export const safeOperationId=value=>typeof value==='string'&&value.length<=96&&/^(?:(?:op|ops|chg|req|run|dep)[-_][A-Za-z0-9][A-Za-z0-9_-]{0,90}|[0-9]{1,20})$/.test(value);
/** The production default is a freshly sampled clock. A numeric clock is retained only for legacy deterministic fixtures; never bind it to caller input. */
const clockReader=clock=>typeof clock==='function'?clock:()=>clock;
const clockValue=clock=>{const sample=clock();return typeof sample==='number'&&Number.isFinite(sample)&&sample>=0?sample:null;};
export const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
export function validate(x){
 if(!exact(x,['operation','idempotency_key','target','params'])||!Object.hasOwn(OPS,x.operation)||!plain(x.target)||!plain(x.params)||typeof x.idempotency_key!=='string'||!/^[A-Za-z0-9._:-]{12,100}$/.test(x.idempotency_key))return 'invalid_operation';
 const t=x.target,p=x.params;
 if(x.operation==='github_workflow_dispatch')return exact(t,['repository','workflow'])&&t.repository===REPO&&t.workflow==='.github/workflows/astra-ingestion-qualification.yml'&&exact(p,['ref','inputs'])&&p.ref==='feat/astra-ingestion-service'&&plain(p.inputs)&&Object.keys(p.inputs).length===0?null:'workflow_outside_scope';
 if(t.workspace_id!==WORKSPACE)return 'workspace_outside_scope';
 if(x.operation==='render_create_worker')return exact(t,['workspace_id'])&&exact(p,['name','repo','branch','runtime','plan','auto_deploy','build_command','start_command'])&&p.name==='astra-operations-worker-candidate'&&p.repo==='https://github.com/'+REPO&&p.branch==='feat/astra-ingestion-service'&&p.runtime==='python'&&p.plan==='free'&&p.auto_deploy===false&&p.build_command==='python -m pip install -r requirements-ingestion.txt'&&p.start_command==='python -m astra_ingestion.worker'?null:'worker_spec_outside_scope';
 if(t.service_id!=='srv-dbh9fko473hc739an8m0'||!exact(t,['workspace_id','service_id']))return 'service_outside_scope';
 if(x.operation==='render_update_worker')return exact(p,['auto_deploy'])&&p.auto_deploy===false?null:'update_outside_scope';
 return exact(p,['environment_group_id'])&&typeof p.environment_group_id==='string'&&/^evg-[a-z0-9]{8,50}$/.test(p.environment_group_id)?null:'group_not_verified';
}
export function validateReceipt(r,x,now){
 if(!exact(r,['controller','site','digest','idempotency_key','operation','scope','owner_confirmation','grant_verified','zero_cost_verified','release_gate_verified','stop','fence','lease','expiry','readback_supported','workflow_dispatch_enabled']))return 'invalid_receipt';
 if(r.controller!==CONTROLLER||r.site!==SITE||r.digest!==digest(x)||r.idempotency_key!==x.idempotency_key||r.operation!==x.operation||r.scope!==OPS[x.operation])return 'wrong_authority_or_digest';
 if(typeof r.owner_confirmation!=='string'||r.owner_confirmation.length<12||r.grant_verified!==true||r.zero_cost_verified!==true||r.release_gate_verified!==true)return 'confirmation_or_grant_missing';
 if(x.operation==='github_workflow_dispatch'&&r.workflow_dispatch_enabled!==true)return 'workflow_not_dispatchable';
 if(r.stop!==false||!Number.isSafeInteger(r.fence)||r.fence<1||typeof r.lease!=='string'||r.lease.length<12)return 'stop_or_fence_failed';
 if(!Number.isSafeInteger(r.expiry)||r.expiry<=now||r.expiry>now+300||r.readback_supported!==true)return 'stale_or_no_readback';
 return null;
}
export async function delegate(x,port,now=()=>Date.now()/1000){
 const current=clockReader(now);
 const sampled=clockValue(current);
 if(sampled===null)return blocked('invalid_clock');
 const v=validate(x);if(v)return blocked(v);
 if(!port||!['inspect','admit','execute','readback'].every(k=>typeof port[k]==='function'))return blocked('controller_port_unbound');
 let prior;try{prior=await port.inspect(x.idempotency_key,digest(x));}catch{return blocked('inspect_unavailable');}
 if(!plain(prior)||prior.digest!==digest(x))return blocked('idempotency_unverified');
 if(prior.state==='complete')return safeOperationId(prior.operation_id)?{state:'complete',executed:false,reused:true,operation_id:prior.operation_id}:blocked('invalid_operation_id');
 if(prior.state!=='absent')return blocked('uncertain_existing_operation_no_retry');
 let receipt;try{receipt=await port.admit(x,digest(x));}catch{return blocked('admission_unavailable');}
 // Inspect/admit are asynchronous: entry-time authorization is not freshness evidence.
 const receivedAt=clockValue(current);if(receivedAt===null)return blocked('invalid_clock');
 const refusal=validateReceipt(receipt,x,receivedAt);if(refusal)return blocked(refusal);
 // Re-read immediately before handing mutation to the controller; it MUST
 // independently serialize stops/fences and repeat this expiry check under guard.
 const dispatchAt=clockValue(current);if(dispatchAt===null)return blocked('invalid_clock');
 if(dispatchAt>=receipt.expiry)return blocked('stale_or_no_readback');
 let result;try{result=await port.execute({request:x,digest:digest(x),fence:receipt.fence,lease:receipt.lease});}catch{return blocked('unknown_execution_outcome_no_retry');}
 if(!plain(result)||result.state!=='accepted'||!safeOperationId(result.operation_id))return blocked('unknown_execution_outcome_no_retry');
 let rb;try{rb=await port.readback(x.idempotency_key,digest(x));}catch{return blocked('readback_unavailable_no_retry');}
 if(!plain(rb)||rb.digest!==digest(x)||!safeOperationId(rb.operation_id)||rb.operation_id!==result.operation_id||!['complete','accepted','pending'].includes(rb.state))return blocked('readback_mismatch_no_retry');
 return {state:rb.state==='complete'?'complete':'accepted_pending',executed:true,operation_id:rb.operation_id};
}
