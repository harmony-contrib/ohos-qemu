"""Only Root-adopted exact seven scopes are unsupported/nonpass; never whole S08."""
from pathlib import Path
from msdp579_contract import ID,need,ref,raw,doc
FACTS_SHA='610e3e0b5a200f2656e7d6efe2d0f5e48f577411b05f091db7497cb52e19f098'
UNSUPPORTED=('stationary-relative-input','device-steady-standing','distance-measurement','metadata-pixel-roundtrip','motion-inference','onscreen-content-control','user-status-inference')

def approved():
 from final579_contract import ROOT,own_sources
 policy=ROOT/'ci/capability-audit/policy579/execution-20261021/unsupported-public-providers.json'
 facts=ROOT/'ci/capability-audit/policy579/execution-20261021/msdp579-public-provider-source-facts.json'
 pinned={r['path']:r['sha256'] for r in doc(own_sources())['files']}
 need(pinned.get(str(policy))==ref(policy)['sha256'] and pinned.get(str(facts))==FACTS_SHA==ref(facts)['sha256'],'Root actual source-admitted partial policy/facts required')
 row=doc(ref(policy))['partial_features']['Msdp579PublicModels'];v=doc(ref(facts))
 need(row['id']==ID and row['whole_id_unsupported'] is False and row['repaired'] is False and row['runtime_pass'] is False and row['new_formal_closure'] is False and row['passable_without_new_runtime'] is False and set(row['positive_scopes'])==set(UNSUPPORTED),'no whole-ID or extra model exclusions')
 need(row['source_facts']['sha256']==FACTS_SHA and set(v['partial_positive_scopes'])==set(UNSUPPORTED) and v['whole_id_unsupported'] is False,'exact bounded source scopes differ')
 for source in (v['official']['archive'],v['official']['complete_tree'],v['official']['complete_archive_inventory'],v['corresponding_sig']['catalog'],v['corresponding_sig']['complete_sig_catalog'],v['corresponding_sig']['entry']):raw(source)
 for scope,value in v['partial_positive_scopes'].items():
  need(value['whole_id_unsupported'] is False and value['positive_supported'] is False and value['repaired'] is False and value['runtime_pass'] is False,'a nonpass model cannot become fixed')
  for source in value['source_evidence']:
   if 'file' in source:raw(source['file'])
 return {k:dict(id=ID,scope=k,disposition='exact_public_provider_positive_unsupported_nonpass',source_facts=ref(facts),policy=ref(policy),runtime_pass=False,repaired=False) for k in UNSUPPORTED}
