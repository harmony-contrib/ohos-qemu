"""Fixed ARM32 normal production inside Root's already-held build container.

No resource owner or Docker command. Gate DATA selects no implementation. The
original Owner35 normal command retains container identity and final disposal.
"""
from pathlib import Path
import hashlib,json,re,tarfile

COMPONENT=Path('patches/common/drivers/peripheral/intelligent_voice/cpu_provider')


def need(value,message):
 if not value:raise ValueError(message)


def ref(path):
 p=Path(path);need(p.is_absolute() and p.resolve()==p and p.is_file() and not p.is_symlink(),'actual canonical regular normal input')
 before=p.stat();h=hashlib.sha256()
 with p.open('rb') as stream:
  for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
 after=p.stat();need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
  (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'normal input changed during read')
 return dict(path=str(p),sha256=h.hexdigest(),bytes=after.st_size)


def checked(row):
 need(type(row)is dict and set(row) in ({'path','sha256'},{'path','sha256','bytes'}),'physical normal Ref2/Ref3 only')
 actual=ref(Path(row['path']));need(actual['sha256']==row['sha256'] and ('bytes' not in row or actual['bytes']==row['bytes']),'actual immutable normal input Ref')
 return Path(actual['path'])


def loads(raw):
 def unique(pairs):
  result={}
  for k,v in pairs:need(k not in result,'duplicate normal DATA key');result[k]=v
  return result
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite normal DATA')))


def doc(row):return loads(checked(row).read_bytes())


def normal_binding(normal_source):
 normal=doc(normal_source);commit=normal['source_commit']
 need(normal['schema']=='postpackage-source579-output/v1' and type(commit)is str and re.fullmatch('[0-9a-f]{40}',commit),
  'real normal SOURCE from the selected development HEAD')
 checked(normal['source_kit_manifest']);checked(normal['canonical_snapshot'])
 return normal


def gate_binding(representative_gate,source_commit):
 """Consume the actual finalized global gate; never invent a pass wrapper."""
 checked(representative_gate);representative_gate={k:representative_gate[k] for k in ('path','sha256')}
 gate=doc(representative_gate)
 need(gate['schema']=='actual-final579-global-raw-gate/v1' and gate['status']=='pass' and
  gate['first_artifact_behavior_gate_passed'] is True and gate['failures']==[],
  'complete actual final QEMU gate required before any ARM32 production')
 packet=doc(gate['packet']);need(packet['schema']=='actual-final579-root-packet/v1' and
  packet['source_commit']==source_commit,'representative gate and selected normal SOURCE commit differ')
 need(gate['original_main_suite']==packet['main_suite'] and gate['original_main_attempt']==packet['main_attempt'],
  'real finalized gate/Main/packet association')
 attempt=doc(gate['raw_actor_attempt']);result=doc(gate['raw_actor_result'])
 need(attempt['schema']=='actual-final579-original-owner-actor-attempt/v1' and attempt['packet']==gate['packet'] and
  attempt['result']==gate['raw_actor_result'] and attempt['source_vector']==gate['source_vector'] and
  attempt['command']['exit_code']==0 and not attempt['command'].get('timed_out',False),
  'complete original final raw actor command and source association')
 checked(dict(path=attempt['command']['log'],sha256=attempt['command']['sha256']));checked(gate['source_vector'])
 need(result['packet']==gate['packet'] and result['source_vector']==gate['source_vector'] and result['failures']==[] and
  result['status']=='raw_union_complete_pending_original_owner_finish' and result['owner_finish_still_required'] is True and
  result['first_artifact_behavior_gate_passed'] is False and result['fullledger']==gate['fullledger'],
  'raw actor alone cannot unlock ARM32; real finalized full ledger must match')
 ledger=gate['fullledger'];need(ledger['obligation_complete'] is True and ledger['effective_unresolved']==[] and ledger['failures']==[],
  'whole supported representative obligations must be complete')
 closures=[gate['main_settlement'],gate['audio_settlement']]+[gate['independent_owner_settlement'][n]['settlement'] for n in ('network','gnss')]
 need(len({r['root'] for r in closures})==4,'four original resource closures remain distinct')
 for row in closures:
  need(row['original_authority_settled'] is True and row['original_constructor_tree_settled'] is True,'actual original final resource settlement')
  checked(row['held']);checked(row['constructors'])
 au=doc(gate['final_au_owner']);need(au['schema']=='actual-dedicated-AU579-owner-result/v1' and
  au['cleanup_verified'] is True and au['audio_runtime_verified'] is True and au['failures']==[],
  'original AU behavior and post-finish record required')
 archive=checked(packet['archive']);boot=doc(packet['main_boot']);env=boot['test_environment']
 need(boot['status']=='pass' and boot['purpose']=='acceptance' and boot['archive_sha256']==packet['archive']['sha256'] and
  env['external_keepalive'] is False and (env['product'],env['device_type'],env['guest_arch'])==('arm64_virt','phone','arm64'),
  'first gate is the newly packaged full representative ARM64 phone QEMU boot')
 root=archive.name.removesuffix('.tar.gz');need(archive.name.endswith('.tar.gz'),'actual normal archive')
 wanted={root+'/build-inputs.json',root+'/manifest.json'};members={}
 with tarfile.open(archive,'r:gz') as stream:
  for member in stream:
   if member.name not in wanted:continue
   need(member.name not in members and member.isfile() and 0<member.size<=8*1024*1024,'unique bounded original package metadata')
   members[member.name]=loads(stream.extractfile(member).read())
 need(set(members)==wanted,'actual representative archive manifests required')
 inputs=members[root+'/build-inputs.json'];manifest=members[root+'/manifest.json'];files=inputs['files_sha256']
 need(inputs['source_git_revision']==source_commit and inputs['tree_sha256']==hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
  'actual same-HEAD complete frozen archive build-input map')
 need((manifest['product'],manifest['device_type'],manifest['guest_arch'])==('arm64_virt','phone','arm64'),
  'representative archive metadata agrees with actual guest')
 here=Path(__file__).resolve().parent
 # Every consumed production module and shared preparation contract is already
 # in the passed archive's frozen source map; no later source mutation is admitted.
 for name in ('produce_arm32.py','normal_arm32_entry.py','build_arm32.py','apply.sh','prepare.py','verify_source.py','INPUT-SOURCES.json','SOURCE-EDITS.json','DEPENDENCIES.json'):
  need(files.get(str(COMPONENT/name))==ref(here/name)['sha256'],'ARM32 normal producer changed after representative gate: '+name)
 return dict(gate=representative_gate,packet=gate['packet'],archive=packet['archive'],main_boot=packet['main_boot'],
  source_commit=source_commit,representative_boot_id=env['boot_id'],source_vector=gate['source_vector'],
  actual_final_gate_consumed=True,arm32_runtime_pass=False)


def preparation_binding(source_root):
 root=Path(source_root);need(root.is_absolute() and root.resolve()==root and root.is_dir() and root!=Path('/'),'actual normal source tree')
 from verify_source import require_final
 require_final(root)  # Fixed shared preparation's full HEAD/source/assets contract; no subprocess.
 here=Path(__file__).resolve().parent;edits=loads((here/'SOURCE-EDITS.json').read_bytes());spec=loads((here/'INPUT-SOURCES.json').read_bytes())
 proofs={}
 def actual(logical,sha):
  relative=Path(logical);need(not relative.is_absolute() and '..' not in relative.parts,'fixed product source member')
  row=ref(root/relative);need(row['sha256']==sha,'normal CPU apply must complete before ARM32 production: '+logical);proofs[logical]=row
 for row in edits['files']:actual(row['path'],row['after_sha256'])
 for logical,row in spec['new_sources'].items():actual(logical,row['sha256'])
 for name,row in spec['models'].items():actual('drivers/peripheral/intelligent_voice/passthrough/cpu/assets/'+name,row['sha256'])
 return dict(source_verifier=ref(here/'verify_source.py'),source_edits=ref(here/'SOURCE-EDITS.json'),input_sources=ref(here/'INPUT-SOURCES.json'),actual_prepared_files=proofs)


def produce(*,normal_source,representative_gate,sdk_native,source_root,build_dir,call):
 checked(normal_source);checked(representative_gate)
 normal_source={k:normal_source[k] for k in ('path','sha256')};representative_gate={k:representative_gate[k] for k in ('path','sha256')}
 normal=normal_binding(normal_source);gate=gate_binding(representative_gate,normal['source_commit']);prepared=preparation_binding(source_root)
 root=Path(source_root);out=Path(build_dir);sdk=Path(sdk_native)
 need(sdk.is_absolute() and sdk.resolve()==sdk and (sdk/'build/cmake/ohos.toolchain.cmake').is_file() and
  out.is_absolute() and out.resolve()==out and out.is_relative_to(root/'out') and not out.exists(),'fixed actual SDK and fresh normal output')
 script=Path(__file__).resolve().with_name('build_arm32.py')
 argv=['python3','-B',str(script),'--source-root',str(root),'--sdk-native',str(sdk),'--cmake','/usr/bin/cmake',
  '--build-dir',str(out),'--normal-source',str(checked(normal_source)),'--normal-source-sha256',normal_source['sha256'],
  '--representative-gate',str(checked(representative_gate)),'--representative-gate-sha256',representative_gate['sha256'],
  '--source-commit',normal['source_commit']]
 # Fixed CLI callback is an ordinary tool subprocess in the current held normal
 # container. Root's original Owner35 records the complete outer command/cleanup.
 receipt=call(argv,'media579_cpu_arm32_normal_source_production')
 need(receipt['exit_code']==0 and receipt.get('timed_out') is False,'actual ARM32 source production failed; preserve original streams')
 result=out/'BUILD.json';value=loads(result.read_bytes())
 need(value['status']=='actual_normal_ARM32_compile_link_ONLY' and value['source_commit']==normal['source_commit'] and
  value['normal_source']==normal_source and value['representative_binding']==gate,'actual completed ARM32 compiler result and real gate association')
 return dict(schema='normal-cpu-voice-arm32-preproduction-result/v2',build=ref(result),command=receipt,
  normal_source=normal_source,representative_gate=representative_gate,representative_binding=gate,prepared=prepared,
  source_commit=normal['source_commit'],runtime_pass=False,first_artifact_behavior_gate_passed=False)
