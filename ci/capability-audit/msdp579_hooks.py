"""Fixed source installers. No resource construction, path/module selectors."""
from pathlib import Path
import time
from msdp579_contract import need,ref,save
from msdp579_runtime import run_local,run_cooperate
from msdp579_image import verify,observe
IMAGE=None
NATIVE=None
def install_native(data):
 global NATIVE
 need(NATIVE is None and type(data)is dict and set(data)=={'binary','build','abi'},'one fixed actual normal addon DATA');NATIVE=data

def attach_native(io):
 need(NATIVE is not None,'normal same-package MSDP addon required')
 from msdp579_admission import admit
 admit(NATIVE,archive_sha256=io.archive_sha256,arch=io.guest.report['test_environment']['guest_arch'])
 existing=dict(io.package_inputs.get('native_addons',{}));existing['msdp579']=NATIVE;io.package_inputs=dict(io.package_inputs,native_addons=existing)


def install_image(proof):
 global IMAGE
 need(IMAGE is None,'normal MSDP image DATA installed once per fixed actor')
 from msdp579_contract import checked
 checked(proof);IMAGE=proof

def run_main(io):
 need(IMAGE is not None,'Root normal same-package Cooperate sidecar required')
 attach_native(io)
 io.msdp579_image=IMAGE
 flow=run_local(io);return flow.data

def paired_network(original_bind):
 def bind(source):
  callbacks=original_bind(source);sink=source.apps579_peer_io;old=callbacks['network'];used=False
  def network(action,parameters):
   nonlocal used
   if action!='msdp579-held':return old(action,parameters)
   need(not used and set(parameters)=={'locals','source_trust','sink_trust'} and IMAGE is not None,'one original trusted two-IO MSDP window')
   used=True;marks={e:(len(o.receipts),len(o.qmp_receipts)) for e,o in (('source',source),('sink',sink))};started=time.monotonic_ns()
   from owning_services579_replay import dfs_peer_identity
   payload=save(Path(source.output)/'msdp579-trusted.json',parameters)
   dfs_peer_identity(payload,source.archive_sha256,source.boot_id,sink.boot_id)
   attach_native(source);attach_native(sink)
   flows=run_cooperate(source,sink,**parameters,trusted_window=payload,image=IMAGE)
   return dict(schema='msdp579-actual-paired-callback/v1',trusted=payload,flows={e:ref(f.path/'flow.json') for e,f in flows.items()},
    started_ns=started,finished_ns=time.monotonic_ns(),endpoints={e:dict(boot_id=o.boot_id,commands=[o.ref_receipt(r) for r in o.receipts[marks[e][0]:]],qmp_records=o.qmp_receipts[marks[e][1]:]) for e,o in (('source',source),('sink',sink))},
    runtime_pass=False,first_artifact_behavior_gate_passed=False)
  return dict(callbacks,network=network)
 return bind


def install_from_native_export(export_ref,*,archive,product):
 from msdp579_contract import doc,checked
 from msdp579_native import prepared_input
 export=doc(export_ref);owner=doc(export['supplemental_owner'])
 need(export['archive']['sha256']==archive['sha256'] and owner['exit_code']==0 and owner['cleanup_verified'] is True and owner['owned_container_absent'] is True and
  set(export['supplemental_builds'])=={'networking579','owning_services579','usb579','msdp579'},'same normal original Owner four singleton receipts')
 data=prepared_input(export['supplemental_builds']['msdp579'],archive=archive,product=product)
 profile=owner['msdp579_actual_path_profile']['source'];checked(profile)
 image=ref(checked(profile).parent/'msdp579-installed-dsos.json')
 need(doc(image)['expanded_profile']==profile,'fixed same normal producer profile/image sidecar association')
 verify(image,archive);install_native(data);install_image(image)
 return dict(native=data,image=image,normal_owner=export['supplemental_owner'],native_export=export_ref)
