"""375 successor of the exact 267 pure peer protocol.

Only fixed env/ps credential observations, current constructor source admission
and complete owner/query census binding extend the predecessor. No IO runs
here; actual root owner, original15 verification and held handles remain required.
Predecessor SHA256: 3da1b6e9549618ac0850b3690d1440f125a9c80e6f4c1f609d0c87545c15b333
"""
"""Pure peer267 protocol: bytes/data only; no resources, filesystem or authority.

Root must supply real raw observations and the real return of the unchanged
original verified_built_case under its owned validator. This module never
attests that external IO happened and never authorizes a resource mutation.
SHA256 here is only the explicitly required byte/prefix digest, not certificate
or cryptographic-tool execution. All original Docker argv remains unchanged.
"""
import ast
from collections import Counter
from batch_network375_root_entry import (PS_ARGV as QUERY_ARGV375, expected_query_uid, process_census)
import copy
import hashlib
import json
from pathlib import PurePosixPath as P
import re

HERE = '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016'
PYTHON = '/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python'
PS_ARGV = QUERY_ARGV375
SOURCE_SHA = {'openvpn-owned-peer-guest15/manifest.json': 'c0098e3fd458ef15a697c08c70077ac985c3c6e8a8957e11921a8a50f39fc8ed', 'openvpn-owned-peer-guest15/common12.py': 'ed92a1033a8547dccc79b357408558979b512691e96dd1560197ea72021e1edc', 'openvpn-owned-peer-guest15/peer_case12.py': 'c77af859005be7029dd486ed9df54edb20306c694146e662191463e03f33c203', 'run_peer_SDK15.py': 'f433a2b4d459866a0a65f8f18ce99e184c69abdd0088296d0b1788d9fac6adda', 'run_peer_guest_steps15.py': '355f5a9b2a50dffb1ca27e4c9afc73e29e3833520d3b2e50f0f79da00a166e23', 'openvpn-owned-peer-review/peer_plan.py': '670b1b5670197880a4b815e6b43ddc100e85394815dbfe184c65845d6d8396c2', 'openvpn-owned-peer-review/peer_lock.json': 'd8fb4eab0e2619e44d8dfc8bbdf11cef6d601a1a41d4219d31272d4c01455282', 'openvpn-owned-peer-capng-review/peer_plan.py': '8111b240b2079a626b822e303f0bb8d5dd69420c30f1966e0f0db42f32e437f9', 'openvpn-owned-peer-capng-review/frozen-base.json': '8d742739efd63c590c93b00e45e1a15c635069a6e281e5b731c6bf1c5db779d3', 'openvpn-owned-peer-capng-review/frozen-netlink.json': '73b08bec201a8c5fc8297979604f628335c528d95232795eea5192dbc90f15cd', 'openvpn-owned-peer-capng-review/peer_lock.json': 'd8fb4eab0e2619e44d8dfc8bbdf11cef6d601a1a41d4219d31272d4c01455282', 'openvpn-owned-peer-capng-review/peer_linux_build.py': 'b3d3761bf91350513a6c3c2b544fe784f98703b0e1db6b52c497d808d812ff32', 'openvpn-owned-peer-capng-review/peer_server.py': '47b08ba30822180bab343439a8de4b726fe5c0a1bee67205df569a32fefca1ff', 'openvpn-owned-peer-capng-review/linux_rtnetlink.py': '1dfe637dbbc1f34644ca5f79a46d1a4a697e8993ae492051b414789cd898fc5c', 'openvpn-owned-peer-capng-review/backend_proof.py': '0ac3622662e2a5fce2207d2e0e346cc03228c9ce105b2aa82ac6dedfeffd9654', 'openvpn-owned-peer-capng-review/source_recipe.py': '18025014e4d5903611533b3159b67dfd9b8eb7696c770e4de2958d41ea584c85', 'openvpn-owned-peer-capng-review/recipe-lock.json': '978ec721fe31446bae69e68beca0fdfd1c995284acaeefe02c6866e1dd82f1d2', 'openvpn-owned-peer-capng-review/configure-peer.patch': 'c183cb8a2f8c9da3b5911d56900e78050de564c76101fbe2428373a8ecbfe5ed'}

class NotReady(ValueError):
    pass


def require(value, message):
    if not value: raise NotReady('NOT_READY: ' + message)


def sha(raw):
    require(type(raw) is bytes, 'actual raw bytes required')
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(rows):
        value = {}
        for key, item in rows:
            require(key not in value, 'duplicate JSON field'); value[key] = item
        return value
    def invalid(value): raise NotReady('NOT_READY: nonfinite JSON')
    require(type(raw) is bytes, 'JSON must be original bytes')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        return all(type(k) is str for k in a) and set(a) == set(b) and all(exact(a[k],b[k]) for k in a)
    if type(a) is list: return len(a) == len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a == b


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def digest(value): return sha(encoded(value))


def path(value):
    require(type(value) is str and value.startswith('/') and not any(x in value for x in ('\x00','\n',',')) and
            str(P(value)) == value and '..' not in P(value).parts, 'literal normalized absolute path required')
    return P(value)


def hash_string(value): return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None

def identity(value): return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None

def positive(value): return type(value) is int and value > 1


def descriptor(value, raw=None, *, fields=3):
    required = {'path','sha256','bytes'} if fields == 3 else {'path','sha256'}
    require(type(value) is dict and set(value) == required and hash_string(value.get('sha256')), 'exact descriptor required')
    path(value['path'])
    if fields == 3: require(type(value['bytes']) is int and value['bytes'] > 0,'positive typed descriptor length required')
    if raw is not None:
        require(sha(raw) == value['sha256'] and (fields != 3 or len(raw) == value['bytes']), 'actual descriptor/raw bytes differ')
    return value


def record_bytes(filename, raw): return dict(path=str(path(filename)),sha256=sha(raw),bytes=len(raw))


def _literal_assignment(tree, name):
    values = [n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    require(len(values)==1,'one pinned source literal required: '+name)
    return ast.literal_eval(values[0])


def source_contract(sources):
    require(type(sources) is dict and set(sources) == set(SOURCE_SHA),'complete exact original source byte set required')
    for name,expected in SOURCE_SHA.items(): require(sha(sources[name])==expected,'original source changed: '+name)
    base=ast.parse(sources['openvpn-owned-peer-review/peer_plan.py'])
    extension=ast.parse(sources['openvpn-owned-peer-capng-review/peer_plan.py'])
    functions=[n for n in base.body if isinstance(n,ast.FunctionDef) and n.name=='config']
    require(len(functions)==1 and len(functions[0].body)==1 and isinstance(functions[0].body[0],ast.Return), 'pinned exact server config return required')
    server=ast.literal_eval(functions[0].body[0].value)
    code=_literal_assignment(extension,'CODE');label=_literal_assignment(base,'LABEL')
    lock=decode(sources['openvpn-owned-peer-capng-review/peer_lock.json'])
    require(sources['openvpn-owned-peer-capng-review/peer_lock.json']==sources['openvpn-owned-peer-review/peer_lock.json'], 'original/derived image+source lock differ')
    recipe=decode(sources['openvpn-owned-peer-capng-review/recipe-lock.json'])
    recipe_source=ast.parse(sources['openvpn-owned-peer-capng-review/source_recipe.py'])
    backend_source=ast.parse(sources['openvpn-owned-peer-capng-review/backend_proof.py'])
    backend_model=dict(required_macros=_literal_assignment(recipe_source,'REQUIRED'),required_symbols=list(_literal_assignment(backend_source,'SYMBOLS')),
        recipe_proof={name:recipe[name]for name in('original_archive_sha256','configure_before_sha256','configure_after_sha256','patch_sha256','only_modified_archive_member','upstream_has_disable_libcapng')})
    backend_model['recipe_proof'].update(configure_argv=_literal_assignment(recipe_source,'CONFIGURE_ARGV'),
        c_h=dict(count=len(recipe['c_h_members_unchanged']),verified_archive_bytes_unchanged=True),identity='derived_test_peer_configure_ONLY_NOT_unmodified_upstream')
    manifest=decode(sources['openvpn-owned-peer-guest15/manifest.json'])
    require(manifest['schema']=='owned-peer15-source-manifest/v1','actual original15 manifest required')
    expected_sources={'manifest.json':SOURCE_SHA['openvpn-owned-peer-guest15/manifest.json'],
                      **{name:row['sha256']for name,row in manifest['files'].items()}}
    require(type(code) is tuple and len(code)==8 and type(label) is str and type(server) is str,'original source literal types differ')
    return dict(label=label,code=list(code),server_config=server,lock=lock,candidate_sources=expected_sources,
                frozen_base=decode(sources['openvpn-owned-peer-capng-review/frozen-base.json']),
                source_sha256=dict(SOURCE_SHA),source_lengths={name:len(raw)for name,raw in sources.items()},source_contract_sha256=digest(SOURCE_SHA),backend_model=backend_model)


def derive_contract(config_raw, config_descriptor, sources):
    """Pure intent admission. Real original config/preflight and file IO remain root obligations."""
    descriptor(config_descriptor,config_raw);c=decode(config_raw);s=source_contract(sources)
    fields={'schema','commit','qa_root','candidate_manifest','archive','runtime_profile','kernel_helper','sdk','signer','credentials','peer','runtime'}
    require(type(c) is dict and set(c)==fields and c['schema']=='openvpn-owned-peer15/v1' and
            type(c['commit'])is str and re.fullmatch('[a-f0-9]{40}',c['commit']) and c['commit']!='c14e803c33f96f5fe01e04378c868fce32aa1487','exact new original15 config required')
    path(c['qa_root'])
    descriptor(c['candidate_manifest'],sources['openvpn-owned-peer-guest15/manifest.json'])
    require(c['candidate_manifest']['path']==HERE+'/openvpn-owned-peer-guest15/manifest.json','actual original15 source directory required')
    for name in ('archive','runtime_profile'):descriptor(c[name])
    require(type(c['kernel_helper'])is dict and set(c['kernel_helper'])=={'root','evidence','timeout_ms'},'exact kernel helper fields required')
    helper=c['kernel_helper'];path(helper['root']);descriptor(helper['evidence'])
    require(helper['evidence']['path']==str(path(helper['root'])/'evidence.json') and type(helper['timeout_ms'])is int and 100<=helper['timeout_ms']<=2000,'exact bounded helper descriptor required')
    require(type(c['sdk'])is dict and set(c['sdk'])=={'output','root','node','ohpm','hvigor','hvigor_cache','java_home'},'exact original SDK fields required')
    for name in ('output','root','hvigor_cache','java_home'):path(c['sdk'][name])
    for name in ('node','ohpm','hvigor'):descriptor(c['sdk'][name])
    require(type(c['signer'])is dict and set(c['signer'])=={'dist','jar'},'exact original signer fields required')
    path(c['signer']['dist']);descriptor(c['signer']['jar'])
    require(type(c['credentials'])is dict and set(c['credentials'])=={'ca','client_cert','client_key','server_cert','server_key'},'five actual original credential descriptors required')
    for row in c['credentials'].values():descriptor(row)
    require(len({r['path']for r in c['credentials'].values()})==5,'distinct actual credential files required')
    p=c['peer'];require(type(p)is dict and set(p)=={'case','run_id','host','host_port','image','source_archive','client_common_name','server_common_name'},'exact original peer fields required')
    case=path(p['case']);descriptor(p['source_archive'])
    require(type(p['run_id'])is str and re.fullmatch('[a-f0-9]{32}',p['run_id']) and p['host']=='10.0.2.2' and
        type(p['host_port'])is int and p['host_port']==54124 and p['image']==s['lock']['base_image'] and
        p['source_archive']['sha256']==s['lock']['source']['archive_sha256'] and p['source_archive']['bytes']==1399858 and
        type(p['client_common_name'])is str and re.fullmatch('[A-Za-z0-9_. -]{1,128}',p['client_common_name']) and
        p['server_common_name']=='qemu-owned-peer' and not any(part in ('source','out')for part in case.parts),'exact original run/host/source/image/CN required')
    require(type(c['runtime'])is dict and set(c['runtime'])=={'output','python','hdc'} and c['runtime']['python']==PYTHON,'exact original literal runtime fields required')
    for value in c['runtime'].values():path(value)
    outputs=[path(c['sdk']['output']),case,path(c['runtime']['output'])]
    protected=[P(HERE).parents[1],path(c['qa_root']),path(c['sdk']['root']),path(helper['root'])]
    require(len(set(outputs))==3,'three distinct outputs required')
    for out in outputs:
        require(all(not out.is_relative_to(r)and not r.is_relative_to(out)for r in protected),'outputs overlap source/SDK/helper')
        require(all(out==other or not out.is_relative_to(other)and not other.is_relative_to(out)for other in outputs),'outputs overlap each other')
        require(all(not path(r['path']).is_relative_to(out)for r in c['credentials'].values()),'credential under mutable output')
    run=p['run_id'];names={role:'owned-vpn-'+role+'-'+run for role in ('build','peer')};names['network']='owned-vpn-net-'+run
    common=['docker','create','--pull=never','--platform=linux/amd64','--read-only','--init','--user=0:0','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=64','--entrypoint=/usr/bin/python3','--tmpfs=/tmp:rw,exec,nosuid,nodev,size=1073741824']
    def mount(src,dst,ro=True):return ['--mount','type=bind,src='+str(src)+',dst='+dst+(',readonly'if ro else'')]
    build=common+['--name',names['build'],'--label',s['label']+'='+run,'--network=none','--cpus=2','--memory=2g']
    build+=mount(case/'code','/peer')+mount(case/'inputs','/inputs')+mount(case/'build','/evidence',False)
    build+=[p['image'],'/peer/peer_linux_build.py','--execute','--archive','/inputs/openvpn-source.tar.gz','--output','/evidence/artifact','--jobs','2']
    peer=common+['--name',names['peer'],'--label',s['label']+'='+run,'--network',names['network'],'--cap-add=NET_ADMIN','--device=/dev/net/tun:/dev/net/tun:rwm','--cpus=1','--memory=512m','--sysctl=net.ipv4.ip_forward=0','--publish','127.0.0.1:54124:1194/udp']
    peer+=mount(case/'code','/peer')+mount(case/'build/artifact','/peer/artifact')+mount(case/'certs','/certs')+mount(case/'runtime','/evidence',False)
    peer+=[p['image'],'/peer/peer_server.py','--execute','--run-id',run,'--output','/evidence/live','--seconds','300']
    plan=dict(schema_version=1,run_id=run,case=str(case),host_port=54124,image=p['image'],build_name=names['build'],peer_name=names['peer'],network_name=names['network'],build_create=build,
        network_create=['docker','network','create','--internal','--driver=bridge','--label',s['label']+'='+run,names['network']],peer_create=peer,
        profile_remote='remote <verified-actual-QEMU-host-path> 54124',execution=False,first_artifact_behavior_gate_passed=False,
        linux_backend='derived configure only: explicit no-capng/no-LZO SITNL; actual macro/object/ELF/nm gates required',
        linux_observation='strict read-only NETLINK_ROUTE raw datagrams; no ip executable')
    result=dict(schema='peer-intent-contract267/v1',config=c,config_descriptor=copy.deepcopy(config_descriptor),source=s,plan=plan,names=names,config_text=config_raw.decode('utf-8'),source_text={name:raw.decode('utf-8')for name,raw in sources.items()},
                scope='pure original-source-derived contract; no actual IO/canonical filesystem/Git/SDK/credentials/runtime authority')
    result['contract_id']=digest(result);return result


def admit_argv(contract, argv, *, phase, observed_ids, context):
    """Classify a full unchanged argv. observed_ids must come from verified registrations.

    This classifier alone grants no stop/rm authority; verify_runtime independently
    re-derives every referenced ID from actual creation/inspect observations.
    """
    checked_contract(contract)
    require(phase in ('build','runtime') and type(observed_ids)is dict and
        set(observed_ids)<=({'build'}if phase=='build'else{'build','peer','network'}) and
        all(identity(v)for v in observed_ids.values()),'typed actual resource IDs required')
    require(type(argv)is list and all(type(x)is str for x in argv) and argv[:1]==['docker'],'original Docker argv must remain literal and unchanged')
    require(type(context)is str and context and '\n'not in context,'actual prefix Docker context required')
    plan,names=contract['plan'],contract['names'];accepted=[]
    def add(expected,action,role=None):
        if exact(argv,expected):accepted.append(dict(action=action,role=role))
    add(['docker','context','show'],'context-show')
    add(['docker','context','inspect',context],'context-inspect')
    add(['docker','image','inspect',plan['image']],'image-inspect')
    roles=('build',)if phase=='build'else('peer','network')
    for role in roles:
        kind='network'if role=='network'else'container'
        add(['docker',kind,'inspect',names[role]],'inspect-name',role)
        if role in observed_ids:
            identifier=observed_ids[role]
            add(['docker',kind,'inspect',identifier],'inspect-id',role)
            if role!='network':
                add(['docker','logs',identifier],'logs',role)
                add(['docker','rm',identifier],'remove',role)
            else:add(['docker','network','rm',identifier],'remove',role)
    if phase=='build':
        add(plan['build_create'],'create','build')
        if 'build'in observed_ids:add(['docker','start','-a',observed_ids['build']],'start','build')
    else:
        add(plan['network_create'],'create','network');add(plan['peer_create'],'create','peer')
        if 'peer'in observed_ids:
            add(['docker','start',observed_ids['peer']],'start','peer')
            # Original frozen cap-ng Controller changes its upstream 10s intent
            # to35 BEFORE actual Popen/journal. This module never rewrites it.
            add(['docker','stop','--time=35',observed_ids['peer']],'stop','peer')
            add(['docker','inspect',observed_ids['peer']],'witness-inspect','peer')
    require(len(accepted)==1,'one exact source-derived full argv required; unknown or changed argv refused')
    return accepted[0]


def _bytes_log(logs, filename, expected):
    require(type(logs)is dict and filename in logs and type(logs[filename])is bytes and sha(logs[filename])==expected,'original actual journal log bytes missing/changed')
    return logs[filename]


def exact_absence(result, kind, subject):
    """Exact original15 subject-specific absence. Query failure never means absence."""
    if not (type(result)is dict and exact(result.get('argv'),['docker',kind,'inspect',subject]) and
            type(result.get('exit_code'))is int and result['exit_code']==1 and
            result.get('timed_out')is False and result.get('error')is None and
            type(result.get('stdout'))is bytes and type(result.get('stderr'))is bytes):return False
    try:
        errors=result['stderr'].decode('utf-8').splitlines()
        allowed={'No such object: '+subject,'Error: No such object: '+subject,'No such '+kind+': '+subject,
            'Error: No such '+kind+': '+subject,'Error response from daemon: No such '+kind+': '+subject}
        if kind=='network':allowed.add('Error response from daemon: network '+subject+' not found')
        return exact(decode(result['stdout']),[])and len(errors)==1 and errors[0]in allowed
    except (ValueError,UnicodeError):return False


def _completed_journal_row(row, logs):
    require(type(row)is dict and type(row.get('argv'))is list and type(row.get('exit_code'))is int and
            not row.get('timed_out') and not row.get('error') and type(row.get('log'))is str and hash_string(row.get('sha256')),
            'actual completed original command/log row required')
    raw=_bytes_log(logs,row['log'],row['sha256'])
    if row['exit_code']==0:return raw
    # Only the original explicit absence adapter may have a successful nonzero
    # control-flow observation. Standard command failure stays failure.
    require(row.get('absence_verified')is True and type(row.get('stdout'))is dict and type(row.get('stderr'))is dict,
            'original nonzero command failure retained')
    stdout=_bytes_log(logs,row['stdout']['path'],row['stdout']['sha256']);stderr=_bytes_log(logs,row['stderr']['path'],row['stderr']['sha256'])
    descriptor(row['stdout'],stdout);descriptor(row['stderr'],stderr)
    require(raw==stdout+stderr and len(row['argv'])==4 and row['argv'][1]in('container','network') and
            exact_absence(dict(argv=row['argv'],exit_code=row['exit_code'],timed_out=False,error=None,stdout=stdout,stderr=stderr),row['argv'][1],row['argv'][3]),
            'original exact absence streams/subject required')
    return raw


def make_runtime_anchor(contract, *, verified_built_case_return, prefix_state_raw, sdk_launcher_raw, challenge_raw, staged_code, prefix_logs):
    """Root MUST call the unchanged real verified_built_case first under its owner.

    The full returned state is required, never a pass/verified boolean. The pure
    join checks it against the real raw snapshot and source-derived plan. It
    cannot attest an external invocation; root must bind that actual call in
    its source-pinned owned validator and preserve the return/raw observations.
    """
    checked_contract(contract)
    state=decode(prefix_state_raw);c,s=contract['config'],contract['source']
    require(type(verified_built_case_return)is dict and exact(state,verified_built_case_return),'real original verified_built_case full return/raw state required')
    require(exact(state.get('plan'),contract['plan']) and state.get('status')=='peer_build_verified_NOT_runtime' and
            state.get('build_removed')is True and type(state.get('ids'))is dict and set(state['ids'])=={'build'} and
            identity(state['ids']['build']) and 'failure'not in state,'new verified build-only exact original state required')
    launcher=decode(sdk_launcher_raw);challenge=decode(challenge_raw)
    require(type(launcher)is dict and type(challenge)is dict,'actual original SDK/challenge objects required')
    launch_desc=record_bytes(str(path(c['sdk']['output'])/'launcher.json'),sdk_launcher_raw)
    challenge_desc=record_bytes(str(path(c['sdk']['output'])/'projects/challenge.json'),challenge_raw)
    require(launcher.get('scope')=='fresh_peer15_two_HAP_SDK_ONLY_NOT_signing_guest_or_TLS' and
        type(launcher.get('exit_code'))is int and launcher['exit_code']==0 and launcher.get('failures')==[] and
        launcher.get('commit')==c['commit'] and launcher.get('run_id')==c['peer']['run_id'] and exact(launcher.get('config'),c) and
        exact(launcher.get('candidate_sources'),s['candidate_sources']) and exact(launcher.get('config_file'),contract['config_descriptor']) and
        exact(launcher.get('driver'),dict(path=HERE+'/run_peer_SDK15.py',sha256=SOURCE_SHA['run_peer_SDK15.py'],bytes=len_source(s,'run_peer_SDK15.py'))),
        'actual same-config original SDK launcher binding required')
    require(exact(challenge.get('config'),c) and challenge.get('run_id')==c['peer']['run_id'] and challenge.get('host_port')==54124 and
        exact(challenge.get('credential_inputs'),{name:{k:v for k,v in c['credentials'][key].items()if k!='bytes'}for name,key in(('ca','ca'),('cert','client_cert'),('key','client_key'))}),
        'actual original SDK challenge/run/credential binding required')
    expected_binding=dict(schema='fresh-peer15-case/v1',config=c,candidate_sources=s['candidate_sources'],SDK_launcher=launch_desc,
        challenge=challenge_desc,run_id=c['peer']['run_id'],host_port=54124,credentials=c['credentials'])
    require(exact(state.get('peer15_binding'),expected_binding),'actual original built-case/SDK/config binding required')
    require(type(staged_code)is dict and set(staged_code)==set(s['code'])|{'server.conf'},'actual staged original CODE and server config bytes required')
    expected_code={name:SOURCE_SHA['openvpn-owned-peer-capng-review/'+name]for name in s['code']}
    require(exact(state.get('code'),expected_code) and all(sha(staged_code[name])==expected_code[name]for name in s['code']) and
        staged_code['server.conf']==s['server_config'].encode(),'actual staged code/config differs from pinned source')
    extension=dict(frozen_receipt=s['frozen_base']['receipt'],frozen_base_sha256=SOURCE_SHA['openvpn-owned-peer-capng-review/frozen-base.json'],
        frozen_netlink_sha256=SOURCE_SHA['openvpn-owned-peer-capng-review/frozen-netlink.json'],
        extension={name:SOURCE_SHA['openvpn-owned-peer-capng-review/'+name]for name in s['code']+['peer_plan.py']})
    require(exact(state.get('netlink_extension'),extension),'original staged extension source join differs')
    backend=state.get('backend_proof')
    require(type(backend)is dict and set(backend)=={'backend_gate','verified','receipt_sha256','binary_sha256','recipe_proof','dependency_proof'} and
        backend['backend_gate']=='actual_derived_configure_cc_macros_objects_SITNL_no_capng_LZO' and
        backend['receipt_sha256']==state.get('build_receipt_sha256') and backend['binary_sha256']==state.get('peer_binary_sha256') and
        hash_string(backend['receipt_sha256']) and hash_string(backend['binary_sha256']), 'full original backend-return/binary/receipt identity required')
    model=s['backend_model'];verified=backend['verified']
    require(type(verified)is dict and set(verified)=={'status','macros','iproute_defined','sitnl_symbols','required_symbols'}and
        verified['status']=='matching_config_macro_object_shape_ONLY'and exact(verified['macros'],model['required_macros'])and verified['iproute_defined']is False and
        exact(verified['required_symbols'],model['required_symbols'])and type(verified['sitnl_symbols'])is list and
        all(type(name)is str and re.fullmatch('net_[A-Za-z0-9_]+',name)for name in verified['sitnl_symbols'])and
        verified['sitnl_symbols']==sorted(set(verified['sitnl_symbols']))and set(model['required_symbols'])<=set(verified['sitnl_symbols'])and
        exact(backend['recipe_proof'],model['recipe_proof'])and exact(backend['dependency_proof'],dict(disabled_capng_lzo_NEEDED_absent=True,undefined_capng_absent=True)),
        'original backend macro/object/recipe/dependency return shape differs')
    commands=state.get('commands');require(type(commands)is list and commands,'complete original external journal prefix required')
    contexts=[];images=[];creates=[]
    for index,row in enumerate(commands):
        filename=path(row['log'])
        require(filename.parent==path(c['peer']['case'])and filename.name.startswith(str(index).zfill(3)+'-')and filename.name.endswith('.log'),'original complete prefix log path/index changed')
        raw=_completed_journal_row(row,prefix_logs)
        if row['argv']==['docker','context','show']:
            context=raw.decode('utf-8').strip();require(context and '\n'not in context,'one actual Docker context required');contexts.append(context)
        if row['argv']==['docker','image','inspect',contract['plan']['image']]:images.append(decode(raw))
        if row['argv']==contract['plan']['build_create']:creates.append(row)
    require(len(contexts)==1 and len(images)==1 and len(creates)==1,'one original build/context/image prefix required')
    image_rows=images[0];require(type(image_rows)is list and len(image_rows)==1,'actual original fixed-image inspect required')
    image=image_rows[0];require(type(image)is dict and type(image.get('Config'))is dict and image.get('Id')==contract['plan']['image']and image.get('Os')=='linux'and image.get('Architecture')=='amd64','actual pinned image/platform required')
    image_labels=image.get('Config',{}).get('Labels')
    require(image_labels is None or type(image_labels)is dict,'typed actual image labels required')
    image_labels=image_labels or{}
    require(type(image_labels)is dict and s['label']not in image_labels,'exact image labels must not pre-own this peer run')
    endpoint_rows=[row for row in commands if row['argv']==['docker','context','inspect',contexts[0]]]
    require(len(endpoint_rows)==1,'actual prefix context inspect required')
    endpoint=decode(_completed_journal_row(endpoint_rows[0],prefix_logs))
    require(type(endpoint)is list and len(endpoint)==1 and type(endpoint[0]['Endpoints']['docker']['Host'])is str and
            endpoint[0]['Endpoints']['docker']['Host'].startswith('unix://'),'actual original local Unix Docker endpoint required')
    expected_prefix=[['docker','context','show'],['docker','context','inspect',contexts[0]],['docker','image','inspect',contract['plan']['image']],
        ['docker','container','inspect',contract['names']['build']],contract['plan']['build_create'],['docker','container','inspect',state['ids']['build']],
        ['docker','start','-a',state['ids']['build']],['docker','container','inspect',state['ids']['build']],['docker','rm',state['ids']['build']]]
    require(exact([row['argv']for row in commands],expected_prefix),'complete original9-row build prefix order/argv required')
    require(commands[3].get('absence_verified')is True and commands[3]['exit_code']==1,'original actual fresh build-name absence required')
    image_context=image_observation(contract,_completed_journal_row(commands[2],prefix_logs))
    inspected=[]
    for index in (5,7):
        rows=decode(_completed_journal_row(commands[index],prefix_logs));require(type(rows)is list and len(rows)==1,'original full build inspect required')
        inspected.append(verify_inspect(contract,dict(image_observation=image_context,image_labels=image_context['image_labels']),rows[0],role='build',observed_ids=state['ids']))
        require(rows[0]['State']['Running']is False,'original build has not settled')
        if index==7:require(type(rows[0]['State'].get('ExitCode'))is int and rows[0]['State']['ExitCode']==0,'original actual native build exit required')
    require(exact(inspected[0],inspected[1]),'original full build container identity changed')
    for row in commands:admit_argv(contract,row['argv'],phase='build',observed_ids=state['ids'],context=contexts[0])
    create_raw=_completed_journal_row(creates[0],prefix_logs).decode('utf-8').strip()
    require(create_raw==state['ids']['build'],'actual original build create/CID prefix differs')
    require(any(row['argv']==['docker','rm',state['ids']['build']]and row['exit_code']==0 for row in commands),'actual original build remove row required')
    result=dict(schema='peer-runtime-prefix267/v1',contract_id=contract['contract_id'],original_state_path=str(path(c['peer']['case'])/'owner-state.json'),
        prefix_raw_sha256=sha(prefix_state_raw),prefix_row_count=len(commands),prefix_rows_sha256=digest(commands),prefix_state=copy.deepcopy(state),
        SDK_launcher=launch_desc,challenge=challenge_desc,docker_context=contexts[0],docker_endpoint=endpoint,image_inspect=image,
        image_labels=image_labels,image_observation=image_observation(contract,
            next(_completed_journal_row(row,prefix_logs)for row in commands if row['argv']==['docker','image','inspect',contract['plan']['image']])),proof_inputs=dict(verified_return=copy.deepcopy(verified_built_case_return),
            sdk_launcher_text=sdk_launcher_raw.decode('utf-8'),challenge_text=challenge_raw.decode('utf-8'),
            staged_code_text={name:raw.decode('utf-8')for name,raw in staged_code.items()},
            prefix_logs_text={name:raw.decode('utf-8')for name,raw in prefix_logs.items()}),
        scope='complete immutable original prefix anchor; no actual resource or invocation attestation')
    result['anchor_id']=digest(result);return result


def len_source(source, name):
    # Source lengths are bound by source_contract from the actual pinned bytes.
    require(name in source['source_lengths'],'actual pinned source length missing')
    return source['source_lengths'][name]


def checked_contract(contract):
    require(type(contract)is dict and type(contract.get('config_text'))is str and type(contract.get('source_text'))is dict and
        all(type(name)is str and type(value)is str for name,value in contract['source_text'].items()),'complete source-derived contract required')
    expected=derive_contract(contract['config_text'].encode('utf-8'),contract['config_descriptor'],
        {name:raw.encode('utf-8')for name,raw in contract['source_text'].items()})
    require(exact(expected,contract),'contract differs from independent original-source derivation')
    return contract


def checked_anchor(contract,anchor,prefix_state_raw):
    require(type(anchor)is dict and type(anchor.get('proof_inputs'))is dict,'complete actual original prefix anchor required')
    inputs=anchor['proof_inputs']
    expected=make_runtime_anchor(contract,verified_built_case_return=inputs['verified_return'],prefix_state_raw=prefix_state_raw,
        sdk_launcher_raw=inputs['sdk_launcher_text'].encode('utf-8'),challenge_raw=inputs['challenge_text'].encode('utf-8'),
        staged_code={name:raw.encode('utf-8')for name,raw in inputs['staged_code_text'].items()},
        prefix_logs={name:raw.encode('utf-8')for name,raw in inputs['prefix_logs_text'].items()})
    require(exact(expected,anchor),'prefix raw SHA/count/complete rows/source/SDK anchor changed')
    return anchor


def immutable_container(value):
    keys=('Id','Name','Created','Image','Path','Args','Config','HostConfig','Mounts','Platform')
    require(type(value)is dict and all(k in value for k in keys),'complete actual immutable container metadata required')
    result=copy.deepcopy({k:value[k]for k in keys});mounts=result['Mounts']
    require(type(mounts)is list and all(type(r)is dict and type(r.get('Destination'))is str and str(path(r['Destination']))==r['Destination']for r in mounts),
            'full typed Mounts objects with normalized unique destinations required')
    require(len({r['Destination']for r in mounts})==len(mounts),'duplicate actual mount destination')
    result['Mounts']=sorted(mounts,key=lambda r:r['Destination']);return result


def verify_inspect(contract,anchor,value,*,role,observed_ids,for_removal=False):
    """Source-derived original identity/security plus complete raw immutable identity.

    Engine-specific fields are never invented: all raw Config/HostConfig/mount
    fields are retained and compared with recursive exact types on later reads.
    """
    checked_contract(contract)
    require(type(anchor)is dict and 'image_observation'in anchor,'actual image observation required, never an invented labels default')
    image_context=anchor['image_observation']
    require(exact(image_context,image_observation(contract,image_context['raw_text'].encode('utf-8')))and exact(anchor.get('image_labels'),image_context['image_labels']),'image labels differ from actual raw fixed-image observation')
    require(role in ('build','peer','network') and type(observed_ids)is dict and role in observed_ids and
            all(identity(v)for v in observed_ids.values()),'actual joined immutable resource ID required')
    require(type(value)is dict and value.get('Id')==observed_ids[role]and type(value.get('Created'))is str and value['Created'], 'actual complete same-CID resource required')
    name=contract['names'][role];label=contract['source']['label'];run=contract['config']['peer']['run_id']
    if role=='network':
        require(value.get('Name')==name and value.get('Internal')is True and value.get('Driver')=='bridge'and
                exact(value.get('Labels'),{label:run})and type(value.get('Containers'))is dict,'actual exact owned internal bridge identity required')
        occupants=value['Containers']
        require(not occupants or 'peer'in observed_ids and set(occupants)=={observed_ids['peer']},'foreign/unknown network occupants preserve network')
        if for_removal:require(not occupants,'network removal requires actual empty occupants')
        return copy.deepcopy({k:v for k,v in value.items()if k!='Containers'})
    config,host=value.get('Config'),value.get('HostConfig')
    require(type(config)is dict and type(host)is dict and type(value.get('State'))is dict and type(value['State'].get('Running'))is bool,'full actual typed container Config/HostConfig/State required')
    create=contract['plan'][role+'_create'];image_index=create.index(contract['plan']['image']);command=create[image_index+1:]
    require(value.get('Name')=='/'+name and value.get('Image')==contract['plan']['image']and value.get('Platform')=='linux'and
        value.get('Path')=='/usr/bin/python3'and exact(value.get('Args'),command)and config.get('Image')==contract['plan']['image']and
        exact(config.get('Cmd'),command)and exact(config.get('Entrypoint'),['/usr/bin/python3'])and config.get('User')=='0:0'and
        exact(config.get('Labels'),dict(anchor['image_labels'],**{label:run})),'actual full original container name/image/command/entrypoint/labels differ')
    require(host.get('Privileged')is False and host.get('ReadonlyRootfs')is True and host.get('PidMode')==''and
        host.get('IpcMode')in('private','')and exact(host.get('CapDrop'),['ALL'])and type(host.get('SecurityOpt'))is list and
        len(host['SecurityOpt'])==1 and type(host['SecurityOpt'][0])is str and host['SecurityOpt'][0].startswith('no-new-privileges')and
        type(host.get('PidsLimit'))is int and host['PidsLimit']==64 and type(host.get('Memory'))is int and
        host['Memory']==(2*1024**3 if role=='build'else 512*1024**2)and type(host.get('NanoCpus'))is int and
        host['NanoCpus']==(2*10**9 if role=='build'else 10**9),'actual exact original security/resource profile differs')
    case=path(contract['config']['peer']['case'])
    expected={('/peer',str(case/'code'),False),('/evidence',str(case/('build'if role=='build'else'runtime')),True)}
    if role=='build':
        expected.add(('/inputs',str(case/'inputs'),False))
        require(host.get('NetworkMode')=='none'and host.get('CapAdd')in(None,[])and host.get('Devices')in(None,[])and host.get('PortBindings')in(None,{}),'offline build caps/devices/network/ports differ')
    else:
        expected.update({('/peer/artifact',str(case/'build/artifact'),False),('/certs',str(case/'certs'),False)})
        ports={'1194/udp':[dict(HostIp='127.0.0.1',HostPort='54124')]}
        require(host.get('NetworkMode')==contract['names']['network']and exact(host.get('CapAdd'),['NET_ADMIN'])and
            exact(host.get('Devices'),[dict(PathOnHost='/dev/net/tun',PathInContainer='/dev/net/tun',CgroupPermissions='rwm')])and
            exact(host.get('PortBindings'),ports),'actual only TUN/NET_ADMIN/loopback contract differs')
        if value['State']['Running']:
            require('network'in observed_ids,'running peer needs actually joined network ID')
            networks=value.get('NetworkSettings',{}).get('Networks')
            require(type(networks)is dict and set(networks)=={contract['names']['network']}and
                networks[contract['names']['network']]['NetworkID']==observed_ids['network']and
                exact(value['NetworkSettings'].get('Ports'),ports),'actual peer network/loopback binding differs')
    normalized=immutable_container(value);binds=[]
    for row in normalized['Mounts']:
        require(row.get('Type')in('bind','tmpfs')and type(row.get('RW'))is bool,'unexpected actual mount kind/RW type')
        if row['Type']=='bind':binds.append((row['Destination'],row.get('Source'),row['RW']))
        else:require(row['Destination']=='/tmp','unexpected tmpfs destination')
    require(len(binds)==len(expected)and set(binds)==expected,'complete original bind mounts differ')
    if for_removal:require(value['State']['Running']is False,'container removal requires actual stopped state')
    return normalized


def verify_prefix_suffix(contract,anchor,prefix_state_raw,current_state_raw):
    checked_anchor(contract,anchor,prefix_state_raw);current=decode(current_state_raw);prefix=anchor['prefix_state']
    require(type(current)is dict and type(current.get('commands'))is list,'complete actual external owner-state required')
    count=anchor['prefix_row_count'];require(len(current['commands'])>=count and
        exact(current['commands'][:count],prefix['commands'])and digest(current['commands'][:count])==anchor['prefix_rows_sha256'],
        'original complete journal prefix mutated/truncated')
    mutable={'commands','ids','status','peer_removed','network_removed','failure'}
    require(exact({k:v for k,v in current.items()if k not in mutable},{k:v for k,v in prefix.items()if k not in mutable}),
            'original prefix plan/config/code/backend/unknown fields changed')
    require(type(current.get('ids'))is dict and set(current['ids'])<= {'build','peer','network'}and
        current['ids'].get('build')==prefix['ids']['build']and all(identity(v)for v in current['ids'].values()),'actual state resource identities invalid/changed')
    require(current.get('status')in('peer_build_verified_NOT_runtime','peer_started_NOT_ready_TLS_or_guest_pass','owned_peer_resources_removed_NOT_guest_cleanup_or_gate'),
            'unknown original runtime state status')
    for key in ('peer_removed','network_removed'):
        if key in current:require(type(current[key])is bool,'typed original removal field required')
    if 'failure'in current:require(type(current['failure'])is str and current['failure'],'original failure must be preserved as actual error text')
    return current,current['commands'][count:]


DOCKER_KEYS={'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','DOCKER_API_VERSION','DOCKER_DEFAULT_PLATFORM'}
CLI97=dict(path='/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r59-F-private-docker-cli-97-01/bin/docker',sha256='70d5a06adf388bd09b652f47ddc9ca31663a3e5353d24188bdb0054b3014ab3e')
TRAMPOLINE216=dict(path=HERE+'/F-runtime-docker-owner216-draft/spawn_trampoline48.py',sha256='11d295e888d0ad46449afa2697680603dc178b62109a534279fac34e4a4b90ef')


def root_binding(contract,anchor,value):
    fields={'schema','nonce','output','constructor_source','docker_cli','spawn_trampoline','daemon_id','docker_environment','query_tools'}
    require(type(value)is dict and set(value)==fields and value['schema']=='peer-root-binding375/v1'and
        type(value['nonce'])is str and re.fullmatch('[a-f0-9]{32}',value['nonce'])and
        value['output']==str(path(contract['config']['runtime']['output']).parent),'actual root nonce/output binding required')
    descriptor(value['constructor_source'],fields=2)
    require((path(value['constructor_source']['path']).is_relative_to(P(HERE)) or path(value['constructor_source']['path']) == P(__file__).with_name('batch_network375_root_entry.py')) and
        exact(value['docker_cli'],CLI97)and exact(value['spawn_trampoline'],TRAMPOLINE216)and
        type(value['daemon_id'])is str and value['daemon_id'],'actual reviewed constructor source/97 CLI/216 utility/daemon required')
    env=value['docker_environment'];require(type(env)is dict and set(env)==DOCKER_KEYS and
        all(v is None or type(v)is str for v in env.values()),'complete actual Docker endpoint environment required')
    expected_query_uid(value['query_tools'], 0)  # structure and exact fixed tool paths, not a UID exemption
    require(anchor['contract_id']==contract['contract_id'],'root binding uses wrong source contract')
    return value


def _actor(contract,anchor,actor,origin,mode,binding):
    require(type(actor)is dict and positive(actor.get('pid'))and positive(actor.get('pgid'))and type(actor.get('uid'))is int and actor['uid']>=0,'actual typed creator identity required')
    if origin=='controller':
        require(set(actor)=={'kind','pid','pgid','uid','entrypoint','argv'}and actor['kind']=='controller'and actor['pid']==actor['pgid']and mode in('start','stop'),'actual owned controller session required')
        expected=dict(path=HERE+'/openvpn-owned-peer-guest15/peer_case12.py',sha256=SOURCE_SHA['openvpn-owned-peer-guest15/peer_case12.py'],bytes=len_source(contract['source'],'openvpn-owned-peer-guest15/peer_case12.py'))
        argv=[PYTHON,expected['path'],'--execute','--config',contract['config_descriptor']['path'],'--sdk-launcher-sha256',anchor['SDK_launcher']['sha256'],'--mode',mode]
        require(exact(actor['entrypoint'],expected)and exact(actor['argv'],argv),'actual original controlled controller entry/argv required')
    else:
        require(set(actor)=={'kind','pid','pgid','uid','source'}and actor['kind']=='guardian'and exact(actor['source'],binding['constructor_source']),'actual reviewed guardian source required for native/read-only stages')
    return actor


def constructor_row(contract,anchor,binding,operation,ledger_snapshots):
    """Join pre-registration to one actual source-pinned final constructor row.

    Root owns persistence and actual Popen handles. No historical PID/PGID here
    confers signal authority. Mutable ledger path+index is bound to its supplied
    actual final raw snapshot, never a circular precomputed future digest.
    """
    ref=operation['constructor'];require(type(ref)is dict and set(ref)=={'ledger_path','index'}and
        type(ref['index'])is int and ref['index']>=0,'one explicit actual constructor reference required')
    filename=str(path(ref['ledger_path']));require(path(filename).is_relative_to(path(binding['output']))and filename in ledger_snapshots,'constructor ledger outside current owned output/missing')
    snapshot=ledger_snapshots[filename];require(type(snapshot)is dict and set(snapshot)=={'descriptor','raw'},'actual raw constructor snapshot required')
    descriptor(snapshot['descriptor'],snapshot['raw']);require(snapshot['descriptor']['path']==filename,'constructor snapshot actual path differs')
    ledger=decode(snapshot['raw'])
    require(type(ledger)is dict and set(ledger)=={'schema','source','nonce','anchor_id','actor','spawns'}and
        ledger['schema']=='peer-owner-constructors375/v1'and exact(ledger['source'],binding['constructor_source'])and
        ledger['nonce']==binding['nonce']and ledger['anchor_id']==anchor['anchor_id']and type(ledger['spawns'])is list and
        ref['index']<len(ledger['spawns']),'actual final source/context/ledger row required')
    row=ledger['spawns'][ref['index']]
    fields={'operation_id','original_argv','final_exec_argv','actual_spawn_argv','previous_signal_mask','effective_environment','state','pid','pgid','uid','exit_code','reaped','start_new_session','stdout_sha256','stderr_sha256','query_tools_before','query_tools_after'}
    require(type(row)is dict and set(row)==fields and row['operation_id']==operation['id']and
        exact(row['original_argv'],operation['argv'])and exact(row['final_exec_argv'],operation['argv']),
        'actual constructor must preserve complete original/final exec argv and operation ID')
    mask=row['previous_signal_mask'];require(type(mask)is list and all(type(v)is int and v>0 for v in mask)and mask==sorted(set(mask))and not({2,15}&set(mask)), 'actual inherited original signal mask must leave INT/TERM unblocked')
    expected=[PYTHON,'-B',TRAMPOLINE216['path'],'--restore-mask',json.dumps(mask),'--',*operation['argv']]
    require(exact(row['actual_spawn_argv'],expected),'actual private trampoline invocation is not independently bound to original final argv')
    env=row['effective_environment'];require(type(env)is dict and set(env)==DOCKER_KEYS|{'PATH'}and
        all(env[k]==v for k,v in binding['docker_environment'].items())and type(env['PATH'])is str and
        env['PATH'].split(':')[0]==str(path(CLI97['path']).parent),'actual private97 PATH/endpoint environment differs')
    require(row['state']=='started'and positive(row['pid'])and positive(row['pgid'])and type(row['uid'])is int and row['uid']>=0 and
        type(row['exit_code'])is int and row['reaped']is True and type(row['start_new_session'])is bool and
        hash_string(row['stdout_sha256'])and hash_string(row['stderr_sha256']), 'unknown/unreaped/never-assigned constructor cannot prove closure')
    actor=_actor(contract,anchor,ledger['actor'],operation['origin'],operation['mode'],binding)
    if operation['origin'] == 'process-cut':
        require(exact(operation['argv'], PS_ARGV) and row['start_new_session'] is True and
            exact(row['query_tools_before'], binding['query_tools']) and
            exact(row['query_tools_after'], binding['query_tools']), 'exact stable query tool chain required')
        expected_uid = expected_query_uid(binding['query_tools'], actor['uid'])
    else:
        require(row['query_tools_before'] is None and row['query_tools_after'] is None,
            'query-only executable credential metadata on non-query command')
        expected_uid = actor['uid']
    require(row['uid']==expected_uid,'actual child host UID differs from exact executable chain')
    if operation['origin']=='controller':
        require(row['start_new_session']is False and row['pgid']==actor['pgid']and row['uid']==actor['uid'],'original Controller subprocess group/uid changed')
    else:require(row['start_new_session']is True and row['pid']==row['pgid'],'root native/read-only child requires its actually registered independent session')
    return row,actor


def _result(operation,row,results):
    require(operation['id']in results,'actual original stdout/stderr result missing')
    result=results[operation['id']]
    fields={'argv','exit_code','timed_out','error','stdout','stderr'}
    require(type(result)is dict and set(result)==fields and exact(result['argv'],operation['argv'])and
        type(result['exit_code'])is int and result['exit_code']==row['exit_code']and result['timed_out']is False and result['error']is None and
        type(result['stdout'])is bytes and type(result['stderr'])is bytes and sha(result['stdout'])==row['stdout_sha256']and
        sha(result['stderr'])==row['stderr_sha256'],'actual result/constructor/raw stream join failed or incomplete')
    return result


def _process_rows(result):
    require(exact(result['argv'],PS_ARGV)and result['exit_code']==0 and result['stderr']==b''and
        result['stdout'].endswith(b'\n')and len(result['stdout'])<=8*1024**2,'complete successful bounded independent process cut required')
    rows=[]
    for line in result['stdout'].decode('utf-8').splitlines():
        words=line.split();require(len(words)==9 and all(p.isdecimal()for p in words[:4]),'complete typed process census row required')
        values=list(map(int,words[:4]));require(all(v>=0 for v in values),'invalid actual process census identity')
        rows.append(dict(pid=values[0],ppid=values[1],pgid=values[2],uid=values[3],birth=' '.join(words[4:])))
    require(rows and len({r['pid']for r in rows})==len(rows),'empty/duplicate/incomplete actual PID census')
    return rows


def verify_runtime(contract,anchor,prefix_state_raw,current_state_raw,*,binding,operations,ledger_snapshots,results,journal_logs,final_cuts):
    """Pure independent protocol/registered-creator/resource-cut verifier.

    closed is conditional on root supplying actual raw observations under its
    real source-pinned owner. It is not lease authority, proof that IO happened,
    guest acceptance or permission to signal a recorded PID/group.
    """
    proof=dict(schema='peer-protocol-settlement375/v1',ready=False,closed=False,original_outcomes_verified=False,
        runtime_validated=False,first_artifact_behavior_gate_passed=False,errors=[],retained_original_failures=[],
        scope='pure exact peer protocol joins only; root actual IO/source/lease/live-handle/VM ownership remains mandatory')
    try:
        current,suffix=verify_prefix_suffix(contract,anchor,prefix_state_raw,current_state_raw);root_binding(contract,anchor,binding)
        require(type(journal_logs)is dict,'actual current complete external journal log byte set required')
        for index,original in enumerate(current['commands']):
            filename=path(original['log'])
            require(filename.parent==path(contract['config']['peer']['case'])and filename.name.startswith(str(index).zfill(3)+'-')and filename.name.endswith('.log'),
                'original external journal log path/index escaped or changed')
            _bytes_log(journal_logs,original['log'],original['sha256'])
        require(type(operations)is list and type(ledger_snapshots)is dict and type(results)is dict,'complete actual operations/constructor/result sets required')
        ids=[op.get('id')for op in operations];seq=[op.get('sequence')for op in operations]
        require(all(type(i)is str and re.fullmatch('[a-f0-9]{32}',i)for i in ids)and len(set(ids))==len(ids)and
            all(type(i)is int and i>0 for i in seq)and seq==list(range(1,len(operations)+1)),'unique actual operation IDs and durable ordered sequence required')
        by_id={op['id']:op for op in operations};ctors={};actors={};actual_results={};used_refs=set()
        fields={'id','sequence','origin','mode','argv','journal_index','constructor'}
        for op in operations:
            require(type(op)is dict and set(op)==fields and op['origin']in('controller','witness','owner-observation','final-query','process-cut'),'exact explicit operation phase required')
            require((op['origin']=='controller'and op['mode']in('start','stop')and type(op['journal_index'])is int and op['journal_index']>=anchor['prefix_row_count'])or
                (op['origin']!='controller'and op['journal_index']is None and op['mode']==('ps'if op['origin']=='process-cut'else'inspect')),
                'operation mode/journal origin invalid')
            row,actor=constructor_row(contract,anchor,binding,op,ledger_snapshots)
            ref=(op['constructor']['ledger_path'],op['constructor']['index']);require(ref not in used_refs,'constructor reused by multiple operations');used_refs.add(ref)
            ctors[op['id']],actors[op['id']]=row,actor;actual_results[op['id']]=_result(op,row,results)
        require(set(results)==set(by_id),'unknown/missing original operation results')
        actual_refs=set()
        for filename,snapshot in ledger_snapshots.items():
            descriptor(snapshot['descriptor'],snapshot['raw']);require(snapshot['descriptor']['path']==filename,'actual ledger path differs')
            ledger=decode(snapshot['raw']);require(type(ledger.get('spawns'))is list,'actual complete dedicated267 ledger required')
            actual_refs.update((filename,index)for index in range(len(ledger['spawns'])))
        require(actual_refs==used_refs,'actual constructor rows omitted/extra; dedicated267 ledger is not a filtered generic ledger')
        observed_ids={'build':anchor['prefix_state']['ids']['build']};creations={}
        for op in operations:
            if op['origin']!='controller':continue
            for role in ('network','peer'):
                if exact(op['argv'],contract['plan'][role+'_create']):
                    require(role not in creations and op['mode']=='start','duplicate create or wrong actual controller phase')
                    result=actual_results[op['id']]
                    require(result['exit_code']==0,'unknown/failed create remains unclosed, never inferred absent')
                    created=result['stdout'].decode('utf-8').strip();require(identity(created),'unknown actual create ID; do not guess absence')
                    require(current['ids'].get(role)==created,'create/actual state/CID-or-networkID assignment gap or substitution')
                    observed_ids[role]=created;creations[role]=op
        require(set(current['ids'])==set(observed_ids),'state adopts an ID without this runtime actual create constructor')
        controller=[op for op in operations if op['origin']=='controller']
        indexes=[op['journal_index']for op in controller]
        require(indexes==list(range(anchor['prefix_row_count'],len(current['commands']))),
            'actual original runtime suffix row omitted/repeated/unassigned constructor')
        journal_create=[];constructor_create=[];seen_identity={}
        for op in operations:
            result=actual_results[op['id']]
            if op['origin']=='process-cut':
                require(exact(op['argv'],PS_ARGV),'only exact bounded independent ps census permitted');continue
            classification=admit_argv(contract,op['argv'],phase='runtime',observed_ids=observed_ids,context=anchor['docker_context'])
            if op['origin']=='witness':require(classification['action']=='witness-inspect','native witness must be exact original Docker inspect/CID')
            if op['origin']in('final-query','owner-observation'):
                require(classification['action']in('inspect-name','inspect-id'),'root observation/cut may only inspect exact owned name/ID')
                if op['origin']=='owner-observation'and result['exit_code']!=0:
                    require(exact_absence(result,'network'if classification['role']=='network'else'container',op['argv'][3]),'unknown owner observation query cannot imply absence')
            if op['origin']=='controller':
                require(classification['action']!='witness-inspect','direct runtime witness cannot be relabelled original Controller journal')
                if classification['action']in('create','start'):require(op['mode']=='start','resource creation/start outside original start phase')
                if classification['action']in('stop','remove','logs'):require(op['mode']=='stop','resource disposal outside original stop phase')
                original=current['commands'][op['journal_index']]
                require(exact(original.get('argv'),op['argv'])and type(original.get('exit_code'))is int and original['exit_code']==result['exit_code']and
                    not original.get('timed_out')and not original.get('error')and type(original.get('log'))is str and
                    original.get('sha256')==sha(result['stdout']+result['stderr']) and
                    _bytes_log(journal_logs,original['log'],original['sha256'])==result['stdout']+result['stderr'],'original suffix argv/outcome/log differs from actual constructor streams')
                if original['exit_code']!=0:
                    absent=(classification['action']=='inspect-name'and original.get('absence_verified')is True and
                        exact_absence(result,'network'if classification['role']=='network'else'container',contract['names'][classification['role']]))
                    if absent:
                        descriptor(original['stdout'],result['stdout']);descriptor(original['stderr'],result['stderr'])
                        require(_bytes_log(journal_logs,original['stdout']['path'],original['stdout']['sha256'])==result['stdout']and
                            _bytes_log(journal_logs,original['stderr']['path'],original['stderr']['sha256'])==result['stderr'],'actual original absence binary files differ')
                    else:proof['retained_original_failures'].append(dict(index=op['journal_index'],argv=op['argv'],exit_code=original['exit_code']))
                if classification['action']=='create':journal_create.append(original['argv']);constructor_create.append(op['argv'])
            if classification['action']in('inspect-name','inspect-id','witness-inspect')and result['exit_code']==0:
                inspected=decode(result['stdout']);require(type(inspected)is list and len(inspected)==1,'actual complete successful inspect JSON required')
                role=classification['role'];require(role in observed_ids,'inspect sees unregistered resource: retain unknown create')
                immutable=verify_inspect(contract,anchor,inspected[0],role=role,observed_ids=observed_ids)
                if role in seen_identity:require(exact(seen_identity[role],immutable),'actual full immutable identity drift')
                else:seen_identity[role]=immutable
            if classification['action']=='context-show'and result['exit_code']==0:
                require(result['stdout'].decode().strip()==anchor['docker_context'],'actual Docker context changed')
            if classification['action']=='context-inspect'and result['exit_code']==0:
                require(exact(decode(result['stdout']),anchor['docker_endpoint']),'actual Docker context endpoint metadata changed')
            if classification['action']=='image-inspect'and result['exit_code']==0:
                image=decode(result['stdout']);require(type(image)is list and len(image)==1 and image[0].get('Id')==contract['plan']['image']and
                    image[0].get('Os')=='linux'and image[0].get('Architecture')=='amd64'and exact(image[0].get('Config'),anchor['image_inspect'].get('Config')),
                    'actual image identity/config changed')
        require(Counter(tuple(a)for a in journal_create)==Counter(tuple(a)for a in constructor_create)and
            Counter(tuple(current['commands'][op['journal_index']]['argv'])for op in controller)==Counter(tuple(op['argv'])for op in controller),
            'original per-invocation exact Counter/multiplicity mismatch')
        require(set(creations)<=set(seen_identity),'created resource lacks actual full inspect identity; no cleanup authority from bare CID')
        require(type(final_cuts)is list and len(final_cuts)==2,'two independent actual final cuts required')
        protected_groups=set();protected_pids=set()
        for op in operations:
            if op['origin']=='controller':protected_groups.add(actors[op['id']]['pgid']);protected_pids.add(actors[op['id']]['pid'])
            if op['origin']in('controller','witness'):protected_groups.add(ctors[op['id']]['pgid']);protected_pids.add(ctors[op['id']]['pid'])
        expected_queries={('network',contract['names']['network']),('container',contract['names']['peer'])}
        for role in creations:expected_queries.add(('network'if role=='network'else'container',observed_ids[role]))
        previous=-1;cut_operations=set()
        work=[op['sequence']for op in operations if op['origin']in('controller','witness','owner-observation')]
        for index,cut in enumerate(final_cuts):
            require(type(cut)is dict and set(cut)=={'index','process_operation','resource_operations'}and type(cut['index'])is int and cut['index']==index and
                type(cut['resource_operations'])is list,'exact independent cut phase required')
            process_id=cut['process_operation'];require(process_id in by_id and by_id[process_id]['origin']=='process-cut'and process_id not in cut_operations,'one unique actual process census constructor per cut')
            ps=by_id[process_id];require(ps['sequence']>previous and all(s<ps['sequence']for s in work),'creator cuts must occur after all actual creating/witness stages')
            query_row = ctors[process_id]; query_actor = actors[process_id]
            query_result = actual_results[process_id]
            rows = process_census(query_result['stdout'], query_result['stderr'], query_result['exit_code'],
                actor=dict(pid=query_actor['pid'], pgid=query_actor['pgid'], effective_uid=query_actor['uid']),
                query=dict(pid=query_row['pid'], uid=query_row['uid']),
                tools_before=query_row['query_tools_before'], tools_after=query_row['query_tools_after'])
            require(not[r for r in rows if r['pgid']in protected_groups or r['pid']in protected_pids],
                'actual registered creator/group still present; no authority to signal historical IDs')
            cut_operations.add(process_id);pairs=set();sequences=[ps['sequence']]
            for operation_id in cut['resource_operations']:
                require(operation_id in by_id and by_id[operation_id]['origin']=='final-query'and operation_id not in cut_operations,'final resource query constructor missing/reused')
                op=by_id[operation_id];require(op['sequence']>ps['sequence'],'resource final query before actual creator census')
                argv=op['argv'];require(len(argv)==4 and argv[1]in('container','network')and argv[2]=='inspect','exact final resource inspect argv required')
                pair=(argv[1],argv[3]);require(pair in expected_queries and pair not in pairs,'unexpected/repeated owned final subject')
                require(exact_absence(actual_results[operation_id],*pair),'failed/unknown/nonempty final query is not resource absence')
                pairs.add(pair);cut_operations.add(operation_id);sequences.append(op['sequence'])
            require(pairs==expected_queries,'final cut omits owned name or actual immutable ID')
            previous=max(sequences)
        require(cut_operations=={op['id']for op in operations if op['origin']in('process-cut','final-query')},'unbound/extra/reused final-cut operations')
        if 'failure'in current:proof['retained_original_failures'].append(dict(original_state_failure=current['failure']))
        proof.update(closed=True,original_outcomes_verified=not proof['retained_original_failures'],
            contract_id=contract['contract_id'],anchor_id=anchor['anchor_id'],prefix_row_count=anchor['prefix_row_count'],
            runtime_suffix_rows=len(suffix),runtime_create_count=len(creations),runtime_original_Docker_create_count=sum(op['argv'][1:2]==['create']for op in controller),
            runtime_network_create_count=sum(op['argv'][1:3]==['network','create']for op in controller),actual_resource_ids={r:observed_ids[r]for r in creations},
            immutable_identities=seen_identity,independent_final_cut_count=2,
            no_original_journal_or_failure_modified=True,signal_authority_granted=False)
    except Exception as error:
        proof['errors'].append(type(error).__name__+': '+str(error))
    return proof


def image_observation(contract,raw):
    """Explicit actual image input for the pre-build phase; never a fabricated profile."""
    checked_contract(contract);rows=decode(raw)
    require(type(rows)is list and len(rows)==1 and type(rows[0])is dict and rows[0].get('Id')==contract['plan']['image']and
        rows[0].get('Os')=='linux'and rows[0].get('Architecture')=='amd64'and type(rows[0].get('Config'))is dict,
        'actual fixed-image/platform/full Config input required')
    labels=rows[0]['Config'].get('Labels')
    require(labels is None or type(labels)is dict,'typed actual image labels required')
    labels=labels or{}
    require(contract['source']['label']not in labels,'image already carries run owner label')
    return dict(schema='peer-image-observation267/v1',raw_sha256=sha(raw),raw_text=raw.decode('utf-8'),image_inspect=rows[0],image_labels=labels)
