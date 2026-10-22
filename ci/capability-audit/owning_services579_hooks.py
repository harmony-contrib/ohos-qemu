"""Fixed root callables. Root constructs/registers/closes every original IO.

No process, VM, socket, lease, native builder or Owner is constructed here.
The ten original capability-input DATA keys are unchanged. This new addon is
an explicit separate already-produced DATA input, never a path selecting code.
"""
from pathlib import Path
import copy
from owning_services579_contract import need,ref,raw,doc,save
from owning_services579_bindings import bind
from owning_services579_runtime import run,run_paired


def admit_native(native,io):
 from owning_services579_admission import admit
 return admit(native,archive_sha256=io.archive_sha256,arch=io.guest.report['test_environment']['guest_arch'])



_MAIN_NATIVE579 = None


def install_main_native(native):
 global _MAIN_NATIVE579
 need(_MAIN_NATIVE579 is None and type(native) is dict and set(native)=={'binary','build','abi'},
  'one fixed Root native DATA installation before original main suite')
 for key in ('binary','build'):
  need(set(native[key])=={'path','sha256'},'actual normal native Ref2');raw(native[key])
 _MAIN_NATIVE579=copy.deepcopy(native)


def main_native(io):
 need(_MAIN_NATIVE579 is not None,'Root must supply actual normal native DATA')
 native=copy.deepcopy(_MAIN_NATIVE579);admit_native(native,io)
 return native


def run_local(io,native):
 io.owner.held_binding(io.guest);need(not io._closed and io.owner.vm is io.guest,'actual original held IO')
 admit_native(native,io);io.owning_services579_native=native
 callbacks=bind(io);result=run(io.guest,callbacks,dict(case='local',run_id=io.run_id,udid=io.udid))
 record=save(Path(io.output)/'six-services579-result.json',result)
 state=callbacks['start'].owning_services579_state
 capture=save(Path(io.output)/'six-services579-capture.json',dict(case='local',run_id=io.run_id,boot_id=io.boot_id,
  archive_sha256=io.archive_sha256,udid=io.udid,cuts=state['cuts'],prepared=state.get('prepared'),installed=state['roles'],result=record))
 attempt={'result':record,'capture':capture};io.six_services579_local_attempt=attempt
 if result.get('cleanup_error'):
  from capability578_stage import UnsettledCapability
  raise UnsettledCapability(result['cleanup_error'])
 if result['failures']:raise RuntimeError('actual six-service business failed; raw retained at '+str(record['path']))
 return attempt


def run_dfs(source,sink,native,*,paired_business):
 """Call after ORIGINAL paired DM PIN auth, before its cleanup/unbind.

paired_business is the original paired report Ref. Network IDs are extracted
from its actual source/sink trusted-device callback raw, not caller parameters.
The exact derivation is in dfs_peer_identity(); no transport boolean is proof.
"""
 from owning_services579_replay import dfs_peer_identity
 pair=dfs_peer_identity(paired_business,source.archive_sha256,source.boot_id,sink.boot_id)
 for io in (source,sink):admit_native(native,io);io.owning_services579_native=native;io.owner.held_binding(io.guest)
 left,right=bind(source),bind(sink)
 result=run_paired(source,sink,left,right,pair)
 record=save(Path(source.output)/'six-services579-dfs-result.json',result)
 captures={}
 for e,io,cb in (('source',source,left),('sink',sink,right)):
  state=cb['start'].owning_services579_state
  captures[e]=save(Path(io.output)/'six-services579-dfs-capture.json',dict(case='dfs',run_id=io.run_id,boot_id=io.boot_id,
   archive_sha256=io.archive_sha256,udid=io.udid,cuts=state['cuts'],prepared=state.get('prepared'),installed=state['roles'],result=record))
 attempt={'result':record,'capture':captures,'paired_business':paired_business}
 source.six_services579_dfs_attempt=attempt;sink.six_services579_dfs_attempt=attempt
 if result.get('cleanup_failures'):
  from capability578_stage import UnsettledCapability
  raise UnsettledCapability('actual DFS cleanup unsettled '+repr(result['cleanup_failures']))
 if result['failures']:raise RuntimeError('actual DFS business failed; raw retained at '+str(record['path']))
 return attempt


def seal_io(io,attempt,*,kind):
 """Only after ORIGINAL io.close; original Owner.finish is still mandatory."""
 need(kind in ('local','dfs-source','dfs-sink') and io._closed,'closed original registered IO before retention')
 report=doc(ref(Path(io.output)/'io.json'));need(report['closed'] is True and report['boot_id']==io.boot_id,'actual closed IO snapshot')
 boot=save(Path(io.output)/('six-services579-'+kind+'-caseboot.json'),copy.deepcopy(io.guest.report))
 value={'schema':'six-owning-services579-closed-IO/v1','kind':kind,'attempt':attempt,'io':ref(Path(io.output)/'io.json'),
  'boot':boot,'build_inputs':ref(io.guest.directory/'build-inputs.json'),'package_manifest':ref(io.guest.directory/'manifest.json'),'device_profile':ref(io.guest.directory/'device-profile.json'),
  'archive_sha256':io.archive_sha256,'boot_id':io.boot_id,'native':io.owning_services579_native,
  'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
 return save(Path(io.output)/('six-services579-'+kind+'-retained.json'),value)


def paired_network(original_bind,native):
 """Compose with Root's existing binder; never replaces the cleanup wrapper."""
 def bind_pair(source):
  callbacks=original_bind(source);sink=source.apps579_peer_io
  need(source is not sink and source.owner.vm is source.guest and sink.owner.vm is sink.guest,'original two endpoint scopes')
  original_network=callbacks['network'];used=False
  def network(action,parameters):
   nonlocal used
   if action!='owning-services579-held':return original_network(action,parameters)
   need(not used and set(parameters)=={'locals','source_trust','sink_trust'},'one fixed early-trusted DFS window')
   marks={e:(len(o.receipts),len(o.qmp_receipts)) for e,o in (('source',source),('sink',sink))}
   used=True;payload=save(Path(source.output)/'six-services579-trusted-window.json',parameters)
   # Both IOs were already registered by the original paired Owner. No
   # additional IO/process/VM is allocated, and its original cleanup is intact.
   result=run_dfs(source,sink,native,paired_business=payload)
   source.six_services579_dfs_attempt=result;sink.six_services579_dfs_attempt=result
   return dict(run_id=source.run_id,archive_sha256=source.archive_sha256,
    source_boot_id=source.boot_id,sink_boot_id=sink.boot_id,attempt=result,
    endpoints={e:dict(boot_id=o.boot_id,udid=o.udid,commands=[o.ref_receipt(r) for r in o.receipts[marks[e][0]:]],
      qmp_records=o.qmp_receipts[marks[e][1]:]) for e,o in (('source',source),('sink',sink))},
    runtime_pass=False,first_artifact_behavior_gate_passed=False)
  return dict(callbacks,network=network)
 return bind_pair


def publish_main(owner,local_io,local_attempt,ads_io,ads_attempt):
 """Root calls after these original registered IOs close, before finish."""
 from ads579_boundaries import seal_ads
 need(local_io.owner is owner and ads_io.owner is owner and local_io.guest is ads_io.guest and
  local_io.archive_sha256==ads_io.archive_sha256 and local_io.boot_id==ads_io.boot_id,'same original main owner/guest')
 local=seal_io(local_io,local_attempt,kind='local');ads=seal_ads(ads_io,ads_attempt)
 return save(owner.output/'six-services579-main-index.json',dict(schema='six-owning-services579-main-retention/v1',
  archive_sha256=local_io.archive_sha256,boot_id=local_io.boot_id,local=local,ads=ads,
  original_owner_finish_still_required=True,runtime_pass=False,first_artifact_behavior_gate_passed=False))


def publish_pair(source,sink):
 """Root's original two scopes/IOs are closed; original settlement still runs."""
 attempt=source.six_services579_dfs_attempt
 need(attempt==sink.six_services579_dfs_attempt and source._closed and sink._closed,'actual closed original paired IOs')
 left=seal_io(source,attempt,kind='dfs-source');right=seal_io(sink,attempt,kind='dfs-sink')
 need(source.owner.parent is sink.owner.parent and source.owner.endpoint=='source' and sink.owner.endpoint=='sink' and
  Path(source.output)==source.owner.output/'business-io' and Path(sink.output)==sink.owner.output/'business-io' and
  source.owner.output.parent==sink.owner.output.parent,'actual original paired endpoint output roots')
 root=source.owner.output.parent;actual=doc(ref(root/'evidence.json'))
 need(actual['schema']=='actual-original-owner-paired579/v1' and actual['run_id']==source.run_id and
  actual['archive']['sha256']==source.archive_sha256,'actual original paired report root')
 return save(root/'six-services579-paired-index.json',dict(schema='six-owning-services579-paired-retention/v1',
  archive_sha256=source.archive_sha256,source=left,sink=right,original_owner_finish_still_required=True,
  runtime_pass=False,first_artifact_behavior_gate_passed=False))


def run_main(local_io,ads_io,native):
 """Fixed business callable on TWO Root-created/registered original IOs.

Root invokes inside its existing main held phase, then closes IOs in its
original resource lifecycle and calls publish_main in a finally retention cut.
Actual failures are aggregated only to attempt the other independent case;
none become a deferred obligation or an acceptance success.
"""
 from ads579_boundaries import run_ads
 need(local_io is not ads_io and local_io.owner is ads_io.owner and
  local_io.guest is ads_io.guest and local_io.boot_id==ads_io.boot_id and
  not local_io._closed and not ads_io._closed,'two original registered IOs on same main guest')
 failures=[];unsettled=[]
 for name,callback in (('local',lambda:run_local(local_io,native)),('ads',lambda:run_ads(ads_io))):
  try:callback()
  except BaseException as error:
   failures.append(dict(case=name,type=type(error).__name__,message=str(error)))
   from capability578_stage import UnsettledCapability
   if isinstance(error,UnsettledCapability):
    unsettled.append(str(error));break
   if not isinstance(error,Exception):raise
 attempt=save(Path(local_io.output)/'six-services579-main-attempt.json',dict(
  schema='six-services579-main-business-attempt/v1',archive_sha256=local_io.archive_sha256,
  boot_id=local_io.boot_id,local=getattr(local_io,'six_services579_local_attempt',None),
  ads=getattr(ads_io,'ads579_boundary_attempt',None),failures=failures,
  original_owner_finish_still_required=True,runtime_pass=False,first_artifact_behavior_gate_passed=False))
 local_io.six_services579_main_attempt=attempt
 if unsettled:
  from capability578_stage import UnsettledCapability
  raise UnsettledCapability('actual six-services/Ads cleanup failed: '+repr(failures))
 if failures:raise RuntimeError('actual six-services/Ads failures preserved: '+repr(failures))
 return attempt
