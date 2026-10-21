"""Bind wallpaper callers/helpers to original build evidence, never build them."""
import json
from pathlib import Path
import struct

from batch_media_wallpaper_runtime import HERE, record, sha, write_json
from batch_media_verify_wallpaper_runtime import checked

HELPERS = {'token': ('wallpaper_token_query', 'wallpaper_receipts/token_query.cpp',
                     {'libaccesstoken_sdk.z.so'}),
           'default': ('wallpaper_default_resolver', 'wallpaper_runtime/default_resolver.cpp',
                       {'libconfigpolicy_util.z.so', 'libcjson.z.so'})}


def caller_sources(item):
    """Check every source in the selected SDK project, including its manifest."""
    project = Path(item['source_project']).resolve()
    evidence = json.loads(checked(item['sdk_evidence']).read_text())
    prefix = item['source_key'].removesuffix('entry/src/main/ets/pages/Index.ets')
    if prefix == item['source_key'] or not prefix or prefix.startswith('/') or '..' in Path(prefix).parts:
        raise ValueError('one actual SDK project prefix required')
    selected = {key[len(prefix):]: value for key, value in evidence['source_files'].items() if key.startswith(prefix)}
    if not {'entry/src/main/ets/pages/Index.ets', 'entry/src/main/module.json5',
            'AppScope/resources/base/element/string.json'} <= selected.keys():
        raise ValueError('SDK source manifest must include page, module and label')
    for relative, digest in selected.items():
        path = project / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink() or sha(path) != digest:
            raise ValueError('actual SDK source changed/escaped: ' + relative)
    return dict(item, compiled_page=record(project/'entry/src/main/ets/pages/Index.ets'))


def elf_dependencies(path, *, product_name='arm64_virt'):
    """Actual class-specific DT_NEEDED; target is bound by the owning raw oracle."""
    import batch_system_build_runtime_helpers as product
    return product.elf_needed(path, product=product_name)


def mapped_record(value,path_map,output_root=None):
    """Relocate immutable private artifacts only; never rewrite the report."""
    original=Path(value['path'])
    if not original.is_absolute()or '..'in original.parts:raise ValueError('unsafe artifact path')
    matches=[]
    for before,after in path_map.items():
        if before not in ('/evidence/helpers','/work')or not Path(after).is_absolute():
            raise ValueError('only explicit old private/fixture prefix mappings are supported')
        if original.is_relative_to(before):matches.append(Path(after)/original.relative_to(before))
    if len(matches)>1:raise ValueError('ambiguous artifact path mapping')
    path=matches[0]if matches else original
    if not path.is_file()and output_root is not None and original.parent==Path('/evidence/helpers'):
        raise ValueError('old private artifact needs an explicit /evidence/helpers path map')
    return record(checked({'path':str(path),'sha256':value['sha256']}))


def installed_runtime_binding(row, needed, inputs):
    """Retain exact installed profile and ELF SONAME identities for every needed DSO."""
    import batch_system_build_runtime_helpers as product
    if needed != row.get('DT_NEEDED') or len(needed) != len(set(needed)):
        raise ValueError('complete actual ELF DT_NEEDED binding required')
    product.validate_installed_profile(row.get('installed_runtime_profile', {}).get('profile'))
    dsos = []
    for soname in needed:
        records = product.runtime_link_records(row, soname)
        if any(inputs.get(item['path']) != item for item in records):
            raise ValueError('installed DSO absent from unchanged actual linker inputs: ' + soname)
        dsos.append({'soname': soname, 'sha256': records[0]['sha256']})
    return {key: row[key] for key in ('installed_runtime_profile', 'actual_link_inputs',
                                     'actual_link_input_sonames')} | {'product_DSOs': dsos}


def verify_runtime_guest_observation(binding, soname, observation, commands, *, target, archive_sha256):
    """Reconstruct the profile-derived command and bind the original transport bytes."""
    import re
    import batch_system_build_runtime_helpers as product
    index = observation.get('command')
    if type(index) is not int or not 0 <= index < len(commands):
        raise ValueError('actual installed DSO observation command missing')
    command = commands[index]; argv = command.get('argv', [])
    script = product.runtime_guest_script(binding, soname)
    if len(argv) != 5 or argv[1:4] != ['-t', target, 'shell'] or command.get('exit_code') != 0:
        raise ValueError('installed DSO command escaped the actual guest')
    marker = re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[-1])
    if marker is None or argv[-1] != script + '; task_ui_rc=$?; printf "\\n' + marker[0] + '%s\\n" "$task_ui_rc"':
        raise ValueError('installed DSO command differs from actual runtime profile')
    transport = checked({k: command[k] for k in ('path', 'sha256')}).read_text().replace('\r', '')
    ending = '\n' + marker[0] + '0\n'
    if transport.count(marker[0]) != 1 or not transport.endswith(ending):
        raise ValueError('installed DSO guest command did not actually succeed')
    raw = checked(observation['actual_hashes']).read_text()
    if transport[:-len(ending)].rstrip('\n') != raw:
        raise ValueError('installed DSO raw bytes differ from actual transport')
    return product.verify_guest_runtime_raw(binding, soname, raw, archive_sha256=archive_sha256)


def helper_binding(name, binary, source, build_file, output_root, path_map=None):
    """Consume the real 0f20ee5 builder report, complete logs and DSO hashes."""
    selector, fixture, required = HELPERS[name]
    build_file=checked(build_file); report=json.loads(build_file.read_text()); root=Path(output_root).resolve()
    builder=HERE/'batch_system_build_runtime_helpers.py'
    path_map=path_map or {}; row=report['helpers'][selector];original=None
    selected_product = row['installed_runtime_profile']['profile']['product']
    scope='diagnostic_new_helpers_using_existing_actual_product_GN_flags_NOT_fresh_GN_target_selection_or_runtime'
    original_ref=None
    if report.get('verify_existing')is True:
        scope='read_only_recheck_of_prior_compile_link_artifacts_and_actual_product_DSO_ELF_ONLY_NOT_runtime'
        origin=report['original_report'];original_ref=mapped_record(origin,path_map,root)
        original=json.loads(checked(original_ref).read_text());old=original['helpers'][selector]
        if (origin.get('rewritten')is not False or origin.get('status')!=original.get('status')or
                original.get('builder_sha256')!=origin.get('builder_sha256')or
                original.get('plan_only')is not False or original.get('changed_inputs')!=[]or
                original.get('product')!=selected_product or
                any(row.get(k)!=old.get(k)for k in ('compile_command','link_command'))):
            raise ValueError('original failed receipt/compile/link history must remain unchanged')
        reused=row['reused_artifacts']
        if (checked(mapped_record(reused['binary'],path_map))!=Path(binary).resolve()or
                sha(checked(mapped_record(reused['source'],path_map)))!=sha(source)):
            raise ValueError('recheck reused another binary or source')
        row={**old,**row}
    if (report.get('scope')!=scope or
            report.get('product')!=selected_product or report.get('plan_only')is not False or report.get('changed_inputs')!=[] or
            report.get('builder_sha256')!=sha(builder) or report.get('first_artifact_behavior_gate_passed')is not False or
            row.get('status')!='pass_compile_link_ONLY' or row.get('fixture')!='batch_media/'+fixture or
            row.get('source',{}).get('sha256')!=sha(source) or row.get('private_source_sha256')!=sha(source) or
            sha(source)!=sha(HERE/'fixtures/batch_media'/fixture) or row.get('binary_sha256')!=sha(binary) or
            row.get('CFI_preserved')is not True or row.get('runtime_validated')is not False):
        raise ValueError('actual unchanged product helper builder/source/CFI proof required')
    from native579_artifact_context import binding_context
    native_context579 = binding_context(original if original is not None else report, row, binary,
        lambda ref: checked(mapped_record(ref, path_map, root)))
    needed=elf_dependencies(binary, product_name=selected_product)
    if needed!=row.get('DT_NEEDED') or not required<=set(needed) or row.get('elf',{}).get('sha256')!=sha(binary):
        raise ValueError('actual helper ELF differs from recorded product dependencies')
    logs=[];commands=[c for c in report['commands']if c['label'].startswith(selector+'-')]
    compile_commands=report['original_commands']if original is not None else report['commands']
    for kind in ('compile','link'):
        selected=[c for c in compile_commands if c['label']==selector+'-'+kind]
        if len(selected)!=1 or selected[0]['argv']!=row[kind+'_command']:raise ValueError('missing exact actual helper compile/link command')
        command=selected[0]
        if command['exit_code']!=0:raise ValueError('actual compile/link failed')
        if original is not None:
            old=[c for c in original['commands']if c['label']==command['label']]
            if len(old)!=1 or any(command[k]!=old[0][k]for k in ('argv','label','log','sha256','exit_code')):
                raise ValueError('original compile/link/log receipt was rewritten')
            logs.append(mapped_record(command['verified_log'],path_map))
        else:logs.append(mapped_record({'path':command['log'],'sha256':command['sha256']},path_map,root))
    if len([c for c in commands if c['label']==selector+'-actual-ELF-ABI'])!=1:
        raise ValueError('actual helper full ELF inspection missing')
    for command in commands:
        if type(command.get('exit_code'))is not int or command['exit_code']!=0 or command.get('timed_out'):
            raise ValueError('selected helper command failed')
        logs.append(mapped_record({'path':command['log'],'sha256':command['sha256']},path_map,root))
    inputs=original['inputs']if original is not None else report['inputs']
    runtime=installed_runtime_binding(row,needed,inputs)
    return {'status':'pass','source_sha256':sha(source),'binary_sha256':sha(binary),'arch':native_context579['arch'],
            'actual_builder_report':record(build_file),'actual_builder_output':str(root),
            'actual_builder_path_map':path_map,'original_build_report':original_ref,
            'original_build_status':original.get('status')if original is not None else report.get('status'),
            'actual_build_logs':logs,'DT_NEEDED':needed,**runtime}


def adapt_helpers(item, output):
    root=Path(item['output_directory']).resolve(); report=json.loads(checked(item['build']).read_text()); result={}
    for name,(selector,fixture,_)in HELPERS.items():
        binary=root/selector/selector; source=HERE/'fixtures/batch_media'/fixture
        original=report['helpers'][selector]['binary']
        if Path(original).parts[-2:]!=(selector,selector):raise ValueError('unexpected actual helper binary layout')
        value=helper_binding(name,binary,source,item['build'],root,item.get('path_map'))
        destination=output/(selector+'-adapted-build.json');write_json(destination,value)
        result[name]={'binary':record(binary),'source':record(source),'build_receipt':record(destination)}
    return result


def verify_helper_receipt(name, binary, source, receipt):
    value=json.loads(checked(receipt).read_text())
    actual=helper_binding(name,binary,source,value['actual_builder_report'],value['actual_builder_output'],value['actual_builder_path_map'])
    if value!=actual:raise ValueError('helper adapter differs from original actual build evidence')
    return value
