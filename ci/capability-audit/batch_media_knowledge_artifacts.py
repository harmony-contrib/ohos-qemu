"""Exact precompiled Knowledge callers and product observer receipts; no builds."""
import json
from pathlib import Path
import re

from batch_media_knowledge_project import FIX, ROLES, READ, WRITE, checked, record, require, sha
from batch_media_knowledge_runtime import validate_challenge
from batch_media_wallpaper_artifacts import elf_dependencies, mapped_record, installed_runtime_binding
from batch_system_build_runtime_helpers import defined_symbol
import batch_apps_contact_picker_coordinator as signatures

HERE = Path(__file__).resolve().parent
HELPER = 'knowledge_token_query'
FIXTURE = 'batch_media/knowledge_runtime/knowledge_token_query.cpp'


def load(path):
    return signatures.load(path)


def role_label(spec, role):
    values = load(Path(spec['source_project']) / 'AppScope/resources/base/element/string.json')['string']
    labels = [v['value'] for v in values if v.get('name') == 'app_name']
    require(labels == ['Knowledge audit ' + role], 'actual compiled SDK role app label differs')
    return labels[0]


def selector(value):
    require(isinstance(value, dict) and set(value) in ({'identifier'}, {'text'}) and
            all(isinstance(v, str) and 0 < len(v) <= 512 for v in value.values()),
            'one exact source/UI id or text required; coordinates prohibited')
    return value


def validate_plan(value, challenge):
    require(set(value) == {'schema_version', 'source_evidence', 'permissions', 'photo_consent'} and
            type(value['schema_version']) is int and value['schema_version'] == 1 and
            isinstance(value['source_evidence'], list) and value['source_evidence'], 'reviewed source/UI plan required')
    for source in value['source_evidence']:
        checked(source)
    require(set(value['permissions']) == {'query', 'curator'}, 'both real permission dialog plans required')
    for role in ('query', 'curator'):
        dialogs = value['permissions'][role]
        require(isinstance(dialogs, list) and 1 <= len(dialogs) <= 2, 'bounded real permission group dialogs required')
        for dialog in dialogs:
            require(set(dialog) == {'bundle', 'title', 'allow'} and dialog['bundle'] == 'com.ohos.permissionmanager',
                    'actual permission manager identity required')
            selector(dialog['title']); selector(dialog['allow'])
            label = 'Knowledge audit ' + role
            permission_texts = [('允许“' + label + '”访问图片和视频？', '允许'),
                                ('Allow ' + label + ' to access images and videos on your device?', 'Allow')]
            require(any(dialog['title'] == {'text': title} and dialog['allow'] == {'text': allow}
                        for title, allow in permission_texts), 'exact actual caller-named permission title/Allow resource required')
    photo = value['photo_consent']
    require(set(photo) == {'bundle', 'title', 'allow'} and
            photo['bundle'] in ('com.ohos.photos', ROLES['importer'][0]), 'real Photos provider or observed importer host required')
    selector(photo['title']); selector(photo['allow'])
    count = len(challenge['cases'])
    consent_texts = [('允许“Knowledge audit importer”保存 ' + str(count) + ' 张图片？', '允许')]
    require(any(photo['title'] == {'text': title} and photo['allow'] == {'text': allow} for title, allow in consent_texts),
            'source-defined exact batch title and actual unique Allow text required; dynamic IDs cannot select Allow')
    return value


def project_binding(spec, role, challenge_path):
    result = signatures.verify_sdk_project(spec)
    data = validate_challenge(challenge_path)
    bundle, apl, permissions, template = ROLES[role]
    source = Path(spec['source_project']).resolve()
    role_label(spec, role)
    manifest_path = checked(spec['source_manifest'])
    require(manifest_path == source / 'knowledge-source-manifest.json', 'exact generated source manifest required')
    manifest = load(manifest_path)
    require(manifest['role'] == role and manifest['run_id'] == data['run_id'] and manifest['bundle_name'] == bundle and
            manifest['challenge'] == record(challenge_path) and manifest['requested_permissions'] == permissions and
            manifest['apl_required_at_signing'] == apl and manifest['system_app_required_at_install'] is (apl != 'normal') and
            manifest.get('sdk_device_types') == ['default'] and manifest.get('acceptance_device') == 'phone' and
            manifest['allowed_acls'] == [] and manifest['restricted_permissions'] == [] and
            manifest['fixture_hashes'] == {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
            'fixed compiled role/challenge/fixture/permission surface differs')
    rows = signatures.source_rows(load(checked(spec['sdk_evidence'])), spec['sdk_project'])
    require(rows.get('knowledge-source-manifest.json') == sha(manifest_path), 'SDK must freeze actual generated manifest')
    for name, checksum in manifest['source_hashes'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                rows.get(name) == checksum and sha(signatures.regular(source / name)) == checksum,
                'actual generated project/source differs: ' + name)
    for name, target in [(template, 'pages/Index.ets'), ('AuditStore.ets', 'model/AuditStore.ets'),
                         ('EntryAbility.ets', 'entryability/EntryAbility.ets')]:
        expected = (FIX / name).read_text().replace('__KNOWLEDGE_RUN__', data['run_id']).replace('__KNOWLEDGE_ROLE__', role)
        require((source / 'entry/src/main/ets' / target).read_text() == expected, 'actual compiled API logic changed')
    module, _ = signatures.hap_contents(checked(spec['unsigned_hap']))
    require(module['app']['bundleName'] == bundle and module['app'].get('debug') is False and
            module['module']['name'] == 'entry' and module['module'].get('extensionAbilities', []) == [] and
            module['module'].get('deviceTypes') == ['default'] and
            module['module'].get('dependencies', []) == [] and
            [p['name'] for p in module['module'].get('requestPermissions', [])] == permissions,
            'actual HAP bundle/module/permission members differ')
    return result


def artifacts(path):
    value = load(path)
    require(set(value) == {'schema_version', 'challenge', 'projects', 'signer', 'helpers', 'ui_plan'} and
            type(value['schema_version']) is int and value['schema_version'] == 1 and
            set(value['projects']) == set(ROLES), 'complete four-role prebuilt Knowledge artifact schema required')
    data = validate_challenge(checked(value['challenge']))
    validate_plan(load(checked(value['ui_plan'])), data)
    require(set(value['signer']) == {'dist', 'jar'}, 'exact signer distribution/jar required')
    signatures.signer_inputs(value['signer']['dist'], checked(value['signer']['jar']))
    for role, spec in value['projects'].items():
        require(set(spec) == {'sdk_evidence', 'sdk_project', 'source_project', 'source_manifest', 'unsigned_hap'},
                'exact SDK project input fields required')
        project_binding(spec, role, checked(value['challenge']))
    require({'build', 'output_directory'} <= set(value['helpers']) <= {'build', 'output_directory', 'path_map'},
            'actual product helper builder receipt/output required')
    return value


def helper_binding(item):
    """Original compile/link or explicit RO recheck, never a fabricated rebuild."""
    build_file = checked(item['build']); report = load(build_file)
    output = Path(item['output_directory']).resolve(); binary = output / HELPER / HELPER
    signatures.regular(binary)
    source = FIX / 'knowledge_token_query.cpp'
    mapping = item.get('path_map', {})
    row = report['helpers'][HELPER]; original = None
    logs = []
    expected_scope = 'diagnostic_new_helpers_using_existing_actual_product_GN_flags_NOT_fresh_GN_target_selection_or_runtime'
    if report.get('verify_existing') is True:
        expected_scope = 'read_only_recheck_of_prior_compile_link_artifacts_and_actual_product_DSO_ELF_ONLY_NOT_runtime'
        origin = report['original_report']; original = load(checked(mapped_record(origin, mapping)))
        require(origin.get('rewritten') is False and origin['status'] == original['status'] and
                origin['builder_sha256'] == original['builder_sha256'] and original.get('plan_only') is False and
                original.get('changed_inputs') == [] and original.get('product') == 'arm64_virt',
                'unchanged actual original helper build receipt required')
        prior = original['helpers'][HELPER]
        require(all(row[k] == prior[k] for k in ('compile_command', 'link_command')), 'recheck changed original compile/link')
        reused = row['reused_artifacts']
        require(checked(mapped_record(reused['binary'], mapping)) == binary and
                sha(checked(mapped_record(reused['source'], mapping))) == sha(source), 'recheck reused different source/binary')
        row = {**prior, **row}
    require(report.get('scope') == expected_scope and report.get('product') == 'arm64_virt' and
            report.get('plan_only') is False and report.get('changed_inputs') == [] and
            report.get('builder_sha256') == sha(HERE / 'batch_system_build_runtime_helpers.py') and
            report.get('first_artifact_behavior_gate_passed') is False and
            row.get('status') == 'pass_compile_link_ONLY' and row.get('fixture') == FIXTURE and
            row.get('source', {}).get('sha256') == sha(source) and row.get('private_source_sha256') == sha(source) and
            row.get('binary_sha256') == sha(binary) and row.get('elf', {}).get('sha256') == sha(binary) and
            row.get('CFI_preserved') is True and row.get('runtime_validated') is False and
            row.get('actual_compiler_dependencies') and row.get('actual_link_inputs') and row.get('anchors'),
            'actual fixed product source/header/CFI/helper receipt required')
    command_rows = report['original_commands'] if original is not None else report['commands']
    for kind in ('compile', 'link'):
        selected = [c for c in command_rows if c['label'] == HELPER + '-' + kind]
        require(len(selected) == 1 and selected[0]['argv'] == row[kind + '_command'] and
                type(selected[0]['exit_code']) is int and selected[0]['exit_code'] == 0, 'actual helper command missing/failed')
        c = selected[0]
        if original is not None:
            old = [v for v in original['commands'] if v['label'] == c['label']]
            require(len(old) == 1 and all(c[k] == old[0][k] for k in ('argv', 'label', 'log', 'sha256', 'exit_code')),
                    'recheck rewrote original actual command/log')
        logs.append(mapped_record(c['verified_log'] if original is not None else {'path': c['log'], 'sha256': c['sha256']}, mapping))
    compile_argv, link_argv = row['compile_command'], row['link_command']
    for argv in (compile_argv, link_argv):
        require('-fsanitize-cfi-cross-dso' in argv and any(v.startswith('-fsanitize=') and 'cfi' in v for v in argv),
                'real cross-DSO CFI command missing')
    require('--target=aarch64-linux-ohos' in compile_argv and '-fno-exceptions' in compile_argv and
            '-pie' in link_argv, 'actual ARM64 product ABI/PIE required')
    private_source = mapped_record({'path': compile_argv[compile_argv.index('-c')+1], 'sha256': sha(source)}, mapping)
    require(sha(checked(private_source)) == sha(source) and
            compile_argv[compile_argv.index('-o')+1] in link_argv and
            checked(mapped_record({'path': link_argv[link_argv.index('-o')+1], 'sha256': sha(binary)}, mapping)) == binary,
            'actual compiler private source/object/link output binding differs')
    commands = [c for c in report['commands'] if c['label'].startswith(HELPER + '-')]
    elf = [c for c in commands if c['label'] == HELPER + '-actual-ELF-ABI']
    require(len(elf) == 1 and Path(elf[0]['argv'][0]).name == 'llvm-readelf' and
            set(('-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle')) <= set(elf[0]['argv']) and
            checked(mapped_record({'path': elf[0]['argv'][-1], 'sha256': sha(binary)}, mapping)) == binary,
            'actual full ELF inspection of this same binary missing')
    for c in commands:
        require(type(c.get('exit_code')) is int and c['exit_code'] == 0 and not c.get('timed_out'), 'actual helper check failed')
        logs.append(mapped_record({'path': c['log'], 'sha256': c['sha256']}, mapping))
    elf_log = checked(mapped_record({'path': elf[0]['log'], 'sha256': elf[0]['sha256']}, mapping)).read_text()
    require(defined_symbol(elf_log, '__cfi_check') and 'std::__h::' in elf_log and 'std::__n1::' not in elf_log,
            'actual CFI/system C++ ABI inspection differs')
    needed = elf_dependencies(binary)
    require(needed == row['DT_NEEDED'] and 'libaccesstoken_sdk.z.so' in needed, 'actual helper dynamic dependencies differ')
    inputs = original['inputs'] if original is not None else report['inputs']
    installed = installed_runtime_binding(row, needed, inputs)
    return dict(binary=record(binary), source=record(source), actual_builder_report=record(build_file),
                actual_logs=logs, DT_NEEDED=needed, **installed, CFI_preserved=True,
                original_status=original['status'] if original is not None else report['status'], runtime_validated=False)
