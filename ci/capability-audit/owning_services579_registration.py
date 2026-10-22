"""Fixed final-actor A26/S03 join. It never runs a guest or trusts case.status."""
from pathlib import Path
import subprocess
from owning_services579_contract import need,ref,raw,doc,save,IDS,original
from owning_services579_records import Evidence
from owning_services579_replay import local_replay,dfs_replay


def collect(packet,output,actor,*,replayed):
 need(subprocess.Popen is actor.ProxyPopen and actor.STATE is not None,'original authenticated final raw actor only')
 from final579_seal import settlement
 original_rows={r['id']:r for r in original()};archive=packet['archive'];main=doc(packet['main_boot'])
 closure=settlement(packet['main_settlement']['held'],packet['main_settlement']['constructors']);root=Path(closure['root'])
 index=doc(ref(root/'six-services579-main-index.json'))
 need(Path(index['local']['path']).is_relative_to(root) and Path(index['ads']['path']).is_relative_to(root),'actual main retained IO roots')
 need(index['schema']=='six-owning-services579-main-retention/v1' and index['archive_sha256']==archive['sha256'] and index['boot_id']==main['test_environment']['boot_id'],'actual main-retained index identity')
 registrations={};failures=[];unresolved=[];parts={};local=None
 try:
  local=Evidence(index['local'],archive,kind='local');need(local.env['boot_id']==main['test_environment']['boot_id'],'actual local services main owning boot')
  parts['local']=local_replay(local);failures+=parts['local']['failures']
 except (ValueError,KeyError,TypeError,IndexError,OSError) as error:failures.append(dict(service='local',error=type(error).__name__+': '+str(error)))
 try:
  pair_index=doc(ref(Path(packet['paired']['report']['path']).parent/'six-services579-paired-index.json'))
  need(pair_index['schema']=='six-owning-services579-paired-retention/v1' and pair_index['archive_sha256']==archive['sha256'],'actual paired index')
  source=Evidence(pair_index['source'],archive,kind='dfs-source');sink=Evidence(pair_index['sink'],archive,kind='dfs-sink')
  proof=doc(replayed['paired']['proof'])['raw_replay'];need(not replayed['paired']['failures'],'original full paired semantic failure')
  parts['DistributedFile']=dfs_replay(source,sink,proof)
 except (ValueError,KeyError,TypeError,IndexError,OSError) as error:failures.append(dict(service='DistributedFile',error=type(error).__name__+': '+str(error)))
 local_complete=parts.get('local',{}).get('services',{})
 six_complete=bool(local and set(local_complete)=={'HiDumper','DataTransitManager','DeviceAuth','DeviceSecurityLevel','PinAuth'} and
  all(r['complete'] for r in local_complete.values()) and parts.get('DistributedFile',{}).get('complete') is True and not failures)
 proof_ref=save(output/'six-services-raw-replay.json',dict(schema='six-owning-services579-full-raw-replay/v1',archive=archive,
  parts=parts,failures=failures,required_obligations_complete=six_complete,runtime_pass=False,first_artifact_behavior_gate_passed=False))
 if six_complete:
  registrations[IDS['services']]=dict(archive_sha256=archive['sha256'],boot_id=local.env['boot_id'],
   related_boot_ids=[source.env['boot_id'],sink.env['boot_id']],evidence=proof_ref,
   original_requirement=original_rows[IDS['services']],resolution='six_existing_owning_service_public_SDK_permission_and_actual_business_raw',
   six_legacy_label_retirement_is_not_a_business_oracle=True,runtime_pass=False)
 else:unresolved.append(dict(id=IDS['services'],scope='all six existing owning-service raw contracts',details=failures))
 ads=None
 try:
  from ads579_boundaries import replay_ads
  ads=replay_ads(index['ads'],archive);need(ads['boot_id']==main['test_environment']['boot_id'],'Ads actual main owning boot')
  # This proposal is NOT active merely because it exists in this capsule.
  # Parent must explicitly compose the exact primary-source partial row into
  # the release policy/new HEAD before any positive-provider exclusion applies.
  from release_scope import partial_provider_policy
  row=partial_provider_policy('phone').get('AdsCompleteProvider579')
  wanted=doc(ref(Path(__file__).with_name('owning_services579')/'ads-partial-row.json'))
  need(row==wanted,'source-bounded Ads positive-provider policy not yet explicitly adopted')
  ads_ref=save(output/'ads-raw-replay.json',ads)
  registrations[IDS['ads']]=dict(archive_sha256=archive['sha256'],boot_id=ads['boot_id'],evidence=ads_ref,
   original_requirement=original_rows[IDS['ads']],resolution='actual_supported_framework_boundaries_with_precise_public_provider_unsupported_nonpass',
   repaired=False,runtime_pass=False,counts_as_whole_provider_fixed=False,positive_provider_supported=False,
   positive_provider_nonpass=True,unsupported_positive_scope=row['scope'])
 except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
  unresolved.append(dict(id=IDS['ads'],scope='complete content/service/UI provider positive flow; framework still mandatory',
   framework=ads,error=type(error).__name__+': '+str(error)))
 output_ref=save(output/'six-services-ads-registration.json',dict(schema='six-owning-services-and-ads579-exact-ID-registration/v1',archive=archive,
  registrations=registrations,failures=failures,unresolved=unresolved,six_service_proof=proof_ref,
  required_obligations_complete=six_complete and not unresolved,original_main_failures_preserved=True,formally_closed=[],runtime_pass=False,first_artifact_behavior_gate_passed=False))
 return dict(registrations=registrations,failures=failures,unresolved=unresolved,proof=output_ref,
  required_obligations_complete=six_complete and not unresolved,original_owner_finish_still_required=True)
