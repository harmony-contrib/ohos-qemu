"""Pure file replay of actual fixed Number build/recheck/ELF/installed DSOs.

No compiler/readelf/Docker/SDK/guest execution. A report boolean is insufficient:
the actual source, artifacts, all raw logs and binary contracts are mandatory.
Root must first produce these through the reviewed fixed private Builder kit.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys

HERE = Path(__file__).resolve().parent
NAME = 'number_token_query395'
VIRTUAL_KIT = PurePosixPath('/number-helper-kit')
VIRTUAL_BUILD = PurePosixPath('/number-helper-output/build')
VIRTUAL_RECHECK = PurePosixPath('/number-helper-recheck/recheck')
VIRTUAL_DSOS = PurePosixPath('/number-helper-output/product-dsos')
BUILDER_SHA = 'eb898a0590c1c5652d6dc10a2addecd5d25a62a77f3a8ca6266e889a7393998d'
OBSERVER_SHA = 'b56d895cddd5dcc375b7b871e871b199540b43c0a495d7ec8b31ff1106a4e5ed'
FIXTURE = 'batch_apps/number_runtime/number_token_query395.cpp'


def need(ok, message):
    if not ok: raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''): h.update(part)
    return h.hexdigest()


def regular(path):
    p = Path(path)
    need(p.is_absolute() and p.resolve() == p and all(not q.is_symlink() for q in (p, *p.parents)),
         'canonical actual artifact required')
    s = p.stat(); need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'one nonalias artifact required')
    return p


def record(path):
    p = regular(path)
    return dict(path=str(p), sha256=digest(p), bytes=p.stat().st_size)


def checked(row):
    need(type(row) is dict and set(row) == {'path', 'sha256', 'bytes'} and
         type(row['bytes']) is int and row['bytes'] >= 0 and re.fullmatch('[a-f0-9]{64}', row['sha256']),
         'exact actual artifact descriptor required')
    need(record(row['path']) == row, 'actual descriptor bytes differ')
    return Path(row['path'])


def decode(path):
    def unique(rows):
        value = {}
        for key, item in rows:
            need(key not in value, 'duplicate actual receipt field'); value[key] = item
        return value
    p = regular(path); need(p.stat().st_size <= 64 * 1024 * 1024, 'bounded actual receipt required')
    return json.loads(p.read_bytes(), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite receipt')))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


def product_module():
    path = HERE / 'helper-kit/ci/capability-audit/batch_system_build_runtime_helpers.py'
    need(digest(regular(path)) == BUILDER_SHA, 'fixed original-guards Number Builder changed')
    return load(path, 'fixed_number_product396')


def relocated(path, origin, directory):
    p = PurePosixPath(path)
    need(p.is_absolute() and p.as_posix() == path and '..' not in p.parts,
         'canonical virtual artifact path required')
    try: relative = p.relative_to(origin)
    except ValueError as error: raise ValueError('artifact outside exact fixed mount') from error
    need(relative.parts, 'actual file below fixed mount required')
    return regular(Path(directory) / Path(*relative.parts))


def commands(report, origin, directory):
    need(type(report.get('commands')) is list and report['commands'], 'actual commands and raw logs required')
    result = {}
    for row in report['commands']:
        need(type(row) is dict and type(row.get('exit_code')) is int and row['exit_code'] == 0 and
             not row.get('timed_out') and type(row.get('argv')) is list and row['argv'] and
             all(type(x) is str for x in row['argv']) and type(row.get('label')) is str,
             'complete successful actual command record required')
        need(row['label'] not in result, 'duplicate actual command label')
        path = relocated(row['log'], origin, directory)
        need(digest(path) == row['sha256'], 'actual command log changed')
        result[row['label']] = row, path
    return result


def needed_from_elf(path):
    """Read actual DT_NEEDED, not a name mention in a tool report."""
    data = regular(path).read_bytes()
    need(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'real ELF64 LE required')
    off = struct.unpack_from('<Q', data, 32)[0]; size, count = struct.unpack_from('<HH', data, 54)
    need(size == 56 and count and off + size * count <= len(data), 'complete actual program headers required')
    loads = []; entries = []
    for i in range(count):
        kind, _, start, va, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', data, off + i * size)
        need(start + length <= len(data), 'ELF segment outside actual file')
        if kind == 1: loads.append((va, start, length))
        if kind == 2:
            need(length % 16 == 0, 'complete dynamic table required')
            entries += [struct.unpack_from('<qQ', data, x) for x in range(start, start + length, 16)]
    tags = {}; offsets = []; ended = False
    for key, value in entries:
        if key == 0: ended = True; break
        if key in (5, 10):
            need(key not in tags, 'ambiguous dynamic string table'); tags[key] = value
        if key == 1: offsets.append(value)
    need(ended and offsets and set(tags) == {5, 10}, 'actual terminated DT_NEEDED table required')
    starts = [start + tags[5] - va for va, start, length in loads if va <= tags[5] and tags[5] + tags[10] <= va + length]
    need(len(starts) == 1, 'unique file-backed dynamic strings required')
    result = []
    for offset in offsets:
        need(offset < tags[10], 'dynamic string offset outside table')
        start = starts[0] + offset; stop = data.find(b'\0', start, starts[0] + tags[10])
        need(stop >= start, 'unterminated DT_NEEDED string')
        name = data[start:stop].decode('ascii')
        need(re.fullmatch(r'[A-Za-z0-9_.+\-]+', name), 'safe exact DT_NEEDED required')
        result.append(name)
    need(len(set(result)) == len(result), 'duplicate DT_NEEDED')
    return set(result)


def image_witness(build, command_table, directory, profile, product):
    """Require the original Builder's actual archive/image re-extractions too."""
    witness=build.get('installed_runtime_image_proof')
    need(type(witness) is dict and set(witness)=={'archive_members','tools','dsos'}, 'actual Builder archive/image witness absent')
    expected={name:dict(archive_member=profile[name+'_image']['archive_member'],
        sha256=profile[name+'_image']['sha256'],bytes=profile[name+'_image']['bytes'])
        for name in ('system','vendor') if name+'_image' in profile}
    need(witness['archive_members']==expected and set(witness['dsos'])==set(profile['dsos']),
         'actual original archive/image inventory differs from same-archive profile')
    tools=witness['tools'];need(set(tools)=={'debugfs','extractor','selector'}, 'actual image extraction tools absent')
    for key,name in (('extractor','ext_image_entries.py'),('selector','verify_alsa_config_image.py')):
        local=HERE/'helper-kit/scripts'/name; row=tools[key]
        need(row==dict(path=str(VIRTUAL_KIT/'scripts'/name),sha256=digest(local),bytes=local.stat().st_size) and
             build['inputs'].get(row['path'])==row, 'actual original image extractor source differs')
    need(build['inputs'].get(tools['debugfs']['path'])==tools['debugfs'], 'actual image tool input hash absent')
    for soname,entry in profile['dsos'].items():
        row=witness['dsos'][soname]; path=relocated(row['path'],VIRTUAL_BUILD,directory)
        staged=entry['staged']; partition=staged['path'].removeprefix('/ohos/out/arm64_virt/packages/phone/').split('/',1)[0]
        need(row.get('partition')==partition and row.get('image_path')==entry['image_member'] and
             row.get('image_path_aliases')==[entry['image_member']] and type(row.get('image_inode')) is int and
             row['image_inode']>0 and digest(path)==row.get('sha256')==staged['sha256'] and
             path.stat().st_size==row.get('bytes')==staged['bytes'] and product.elf_soname(path)==soname,
             'actual original image dump inode/aliases/full bytes/SONAME differ')
        key='installed-runtime-stat-'+soname
        need(key in command_table and type(row.get('stat_command')) is int and
             build['commands'][row['stat_command']]==command_table[key][0], 'actual original image stat command binding absent')
        command,log=command_table[key]
        need(command['argv']==[tools['debugfs']['path'],'-R','stat '+entry['image_member'],profile[partition+'_image']['path']] and
             re.search(r'(?m)^Inode: '+str(row['image_inode'])+r'\s+Type: regular\s',log.read_text()),
             'actual original image raw stat inode differs')


@dataclass(frozen=True)
class AdmittedObserver:
    binary: Path
    binary_record: dict
    helper: dict
    profile: dict
    needed: tuple
    evidence: dict


def admit(proof, *, profile_descriptor, archive_sha256):
    need(type(proof) is dict and set(proof) == {'build', 'recheck', 'dsos'},
         'actual build + independent recheck + DSO export descriptors required, never readiness bool')
    product = product_module()
    build_path, recheck_path, dsos_path = (checked(proof[k]) for k in ('build', 'recheck', 'dsos'))
    need(build_path.name == recheck_path.name == 'build.json' and dsos_path.name == 'manifest.json' and
         build_path != recheck_path and build_path.parent != recheck_path.parent,
         'separate actual original/recheck directories required')
    build, review, exports = (decode(p) for p in (build_path, recheck_path, dsos_path))
    profile_path = checked(profile_descriptor); profile = decode(profile_path)
    product.validate_installed_profile(profile, archive_sha256=archive_sha256)
    need(profile['device'] == 'phone' and profile['source_root'] == '/ohos', 'actual new phone source/profile required')
    for report in (build, review):
        need(report.get('status') == 'pass_compile_link_ONLY' and report.get('plan_only') is False and
             report.get('product') == 'arm64_virt' and report.get('source_root') == '/ohos' and
             report.get('build_directory') == '/ohos/out/arm64_virt' and report.get('changed_inputs') == [] and
             report.get('builder_sha256') == BUILDER_SHA and set(report.get('helpers', {})) == {NAME} and
             report.get('requirements_closed') == 0 and report.get('first_artifact_behavior_gate_passed') is False,
             'actual fixed Number build/recheck/source scope differs')
    old, new = build['helpers'][NAME], review['helpers'][NAME]
    need(old.get('fixture') == FIXTURE and old.get('status') == new.get('status') == 'pass_compile_link_ONLY' and
         old.get('runtime_validated') is False and new.get('runtime_validated') is False and
         old.get('CFI_preserved') is True and new.get('CFI_preserved') is True,
         'actual completed original and rechecked CFI diagnostic required')
    source = old.get('source', {})
    need(source.get('path') == str(VIRTUAL_KIT / 'ci/capability-audit/fixtures' / FIXTURE) and
         source.get('sha256') == OBSERVER_SHA and old.get('private_source_sha256') == OBSERVER_SHA and
         source == build.get('inputs', {}).get(source.get('path')) and
         product._runtime_profile(old, archive_sha256) == profile and
         old['installed_runtime_profile'] == build['installed_runtime_profile'] == new['installed_runtime_profile'],
         'actual fixed observer source/profile binding differs')
    expected_profile = dict(path='/runtime-profile/runtime-profile.json', sha256=profile_descriptor['sha256'], bytes=profile_descriptor['bytes'])
    need(build['installed_runtime_profile']['source'] == expected_profile and
         review.get('verify_existing') is True and review.get('original_report') == dict(
             path=str(VIRTUAL_BUILD / 'build.json'), sha256=proof['build']['sha256'],
             status=build['status'], builder_sha256=BUILDER_SHA, rewritten=False),
         'independent original report/profile recheck differs')
    actual_commands = commands(build, VIRTUAL_BUILD, build_path.parent)
    checked_commands = commands(review, VIRTUAL_RECHECK, recheck_path.parent)
    image_witness(build,actual_commands,build_path.parent,profile,product)
    originals = review.get('original_commands')
    need(type(originals) is list and len(originals) == len(actual_commands), 'independent replay must bind every original command')
    for row in originals:
        original = dict(row); verified = original.pop('verified_log', None)
        need(original['label'] in actual_commands and original == actual_commands[original['label']][0] and
             type(verified) is dict and verified.get('sha256') == original['sha256'], 'original command replay mismatch')
    need(len({row['label'] for row in originals})==len(originals),'duplicate original command replay')
    compile_cmd, link_cmd = old['compile_command'], old['link_command']
    product.validate_flags(compile_cmd)
    need(product.effective_cfi(link_cmd) and any(w == '-flto' or w.startswith('-flto=') for w in link_cmd), 'actual link CFI/LTO absent')
    for label, argv in ((NAME+'-compile', compile_cmd), (NAME+'-link', link_cmd)):
        need(label in actual_commands and actual_commands[label][0]['argv'] == argv, 'actual compile/link raw command differs')
    origin = VIRTUAL_BUILD / NAME
    source_path = relocated(str(origin / 'number_token_query395.cpp'), VIRTUAL_BUILD, build_path.parent)
    guard = relocated(str(origin / 'actual_system_abi.h'), VIRTUAL_BUILD, build_path.parent)
    obj = relocated(str(origin / (NAME+'.o')), VIRTUAL_BUILD, build_path.parent)
    binary = relocated(str(origin / NAME), VIRTUAL_BUILD, build_path.parent)
    deps = relocated(str(origin / 'headers.d'), VIRTUAL_BUILD, build_path.parent)
    need(digest(source_path) == OBSERVER_SHA and source_path.stat().st_size == source['bytes'] and
         guard.read_text() == product.ABI_GUARD and digest(guard) == old['abi_guard_sha256'] and obj.stat().st_size > 0 and
         digest(deps) == old['depfile_sha256'], 'actual source/guard/object/depfile artifact differs')
    object_bytes=obj.read_bytes()
    object_kind=(object_bytes.startswith((b'BC\xc0\xde',b'\xde\xc0\x17\x0b')) or
                 len(object_bytes)>=20 and object_bytes[:7]==b'\x7fELF\x02\x01\x01' and
                 struct.unpack_from('<HH',object_bytes,16)==(1,183))
    need(object_kind,'actual LTO bitcode or AArch64 relocatable object artifact required')
    need(product.argument(compile_cmd, '-c') == str(origin/'number_token_query395.cpp') and
         product.argument(compile_cmd, '-o') == str(origin/(NAME+'.o')) and
         product.argument(compile_cmd, '-include') == str(origin/'actual_system_abi.h') and
         product.argument(compile_cmd, '-MF') == str(origin/'headers.d') and
         product.argument(link_cmd, '-o') == str(origin/NAME) and str(origin/(NAME+'.o')) in link_cmd,
         'actual compile/link artifact argv differs')
    expected_compiler='/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++'
    need(compile_cmd[0] == link_cmd[0] == expected_compiler, 'actual product compiler only; no SDK compiler')
    dependencies = old.get('actual_compiler_dependencies', [])
    need(dependencies and new.get('actual_compiler_dependencies') == dependencies and
         review.get('original_input_count') == len(build.get('inputs', {})),
         'actual independently rechecked full depfile/header inventory differs')
    for header in ('accesstoken_kit.h', 'hap_token_info.h'):
        matches=[r for r in dependencies if r['path'] == '/ohos/base/security/access_token/interfaces/innerkits/accesstoken/include/'+header]
        need(len(matches)==1 and matches[0] == build['inputs'].get(matches[0]['path']), 'actual target AccessToken header dependency absent')
    artifacts = new.get('reused_artifacts', {})
    expected_artifacts = {'source':source_path, 'abi_guard':guard, 'object_new_hash_capture':obj, 'binary':binary, 'depfile':deps}
    need(set(artifacts) == set(expected_artifacts), 'actual rechecked source/object/ELF/depfile evidence absent')
    for name, actual in expected_artifacts.items():
        row=artifacts[name]
        need(digest(actual)==row.get('sha256') and actual.stat().st_size==row.get('bytes') and
             relocated(row['path'],VIRTUAL_BUILD,build_path.parent)==actual,
             'independent rechecked artifact bytes differ: '+name)
    elf = product.elf_header(binary, executable=True)
    need(elf == old.get('elf') == new.get('elf') and elf['sha256'] == old.get('binary_sha256') == new.get('binary_sha256'),
         'actual original/rechecked ELF bytes differ')
    symbols = load(HERE/'helper-kit/scripts/verify_runtime_elf_contract.py','fixed_number_elf396').read_elf(binary)
    all_symbols = symbols.defined | symbols.undefined
    need(symbols.machine == 183 and '__cfi_check' in symbols.defined and any('St3__h' in s for s in all_symbols) and
         not any('St4__n1' in s for s in all_symbols), 'actual ELF cross-DSO CFI/system __h ABI absent or SDK __n1 present')
    needed = needed_from_elf(binary)
    need('libaccesstoken_sdk.z.so' in needed and needed == set(old.get('DT_NEEDED', [])) == set(new.get('DT_NEEDED', [])),
         'actual ELF DT_NEEDED differs from original/recheck')
    for index, (table, helper) in enumerate(((actual_commands, old), (checked_commands, new))):
        key=NAME+'-actual-ELF-ABI'; need(key in table, 'actual ELF raw inspection absent')
        cmd, log=table[key]; text=log.read_text()
        need(cmd['argv'] == ['/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-readelf','-h','-l','-d','--dyn-syms','--wide','--demangle',str(origin/NAME)] and
             product.defined_symbol(text,'__cfi_check') and 'std::__h::' in text and 'std::__n1::' not in text and
             product.dynamic_needed(text)==needed,'actual raw ELF inspection differs from actual binary')
        for soname in needed: product.runtime_link_records(helper,soname)
    need(exports.get('scope') == 'fresh installed-runtime actual linker-opened DT_NEEDED full-byte export ONLY_NOT_guest' and
         exports.get('source_root') == '/ohos' and exports.get('build_receipt') == dict(
             path=str(VIRTUAL_BUILD/'build.json'),sha256=proof['build']['sha256'],bytes=proof['build']['bytes']) and
         exports.get('runtime_profile') == build['installed_runtime_profile'] and set(exports.get('files', {}))==needed,
         'actual full linker-opened DSO export differs')
    export_records={}
    for soname in needed:
        row=exports['files'][soname]; selected,=product.runtime_link_records(old,soname)
        path=relocated(row['path'],VIRTUAL_DSOS,dsos_path.parent)
        need(path.name==soname and row.get('original')==selected and row.get('helpers')==[NAME] and
             digest(path)==row.get('sha256')==selected['sha256'] and path.stat().st_size==row.get('bytes')==selected['bytes'] and
             product.elf_soname(path)==soname,'actual exported installed DSO full bytes/SONAME differ')
        export_records[soname]=record(path)
        if soname=='libaccesstoken_sdk.z.so':
            key=NAME+'-linked-'+soname
            need(key in actual_commands and key in checked_commands,'actual AccessToken DSO ELF/CFI raw checks absent')
            for table in (actual_commands,checked_commands):
                need(product.defined_symbol(table[key][1].read_text(),'__cfi_check'),'actual AccessToken DSO raw CFI definition absent')
            actual_symbols=load(HERE/'helper-kit/scripts/verify_runtime_elf_contract.py','fixed_number_dso396').read_elf(path)
            need('__cfi_check' in actual_symbols.defined,'actual AccessToken DSO binary CFI definition absent')
    for descriptor in (*proof.values(),profile_descriptor): checked(descriptor)
    return AdmittedObserver(binary=binary,binary_record=record(binary),helper=old,profile=profile,needed=tuple(sorted(needed)),
        evidence=dict(original_proof=proof,profile=profile_descriptor,actual_source=record(source_path),
                      actual_ELF=record(binary),actual_exported_DSOs=export_records,
                      scope='actual fixed compile/recheck/ELF/profile replay ONLY; no guest permission/provider claim'))
