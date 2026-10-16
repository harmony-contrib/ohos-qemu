"""Exact communication TU map plus regenerated real Rust CXX/RIL header inputs."""
import hashlib
import json
from pathlib import Path
import subprocess

MAP = 'docs/capability-audit/parallel/location/round7-communication-build-map.json'
COMPONENT = 'patches/common/base/telephony/state_registry/communication_state'
CXX = 'base/telephony/state_registry/frameworks/ets/ani/observer/src/wrapper.rs'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def group(repo):
    data = json.loads((repo / MAP).read_text())
    manifest = json.loads((repo / COMPONENT / 'source_states.json').read_text())
    project = 'base/telephony/state_registry'
    result = {'project': project, 'revision': manifest['projects'][project],
              'additional_projects': {n: v for n, v in data['fixed_project_HEADs'].items() if n != project},
              'components': ['communication_state'], 'extra_owned_paths': manifest['files'],
              'units': [], 'source_paths': {}, 'targets': {}, 'generate_communication': True,
              'required_header': None, 'supported_products': ['arm64_virt'],
              'extra_recipe': [MAP, 'ci/capability-audit/communication_build_inputs.py'],
              'scope': 'sixteen_complete_communication_TU_variants_plus_actual_regenerated_CXX_wrapper_NOT_Rust_link_or_runtime'}
    for row in data['translation_units']:
        for variant in row['variants']:
            unit = Path(row['source_project_relative_path']).stem + '__' + Path(variant['object_target']).parent.name
            if unit in result['units']: raise ValueError('duplicate communication object identity')
            result['units'].append(unit)
            result['source_paths'][unit] = row['source_project_relative_path']
            result['targets'][unit] = variant['object_target']
    wrapper = data['rust_and_cxxbridge']['wrapper_compilation']
    result['units'].append('generated_wrapper')
    result['targets']['generated_wrapper'] = wrapper['object_target']
    return result


def generate(repo, root, staged, output, ril):
    if ril is None: raise ValueError('actual verified regenerated RIL checkpoint required')
    data = json.loads((repo / MAP).read_text())
    evidence = json.loads((ril / 'evidence.json').read_text())
    if (evidence.get('status') != 'pass' or evidence.get('first_artifact_behavior_gate_passed') is not False or
            evidence.get('generator_sha256') != sha(root / 'out/arm64_virt/clang_x64/ability/idl_tool/idl') or
            any(sha(root / n) != h for n, h in evidence['source_inputs_sha256'].items())):
        raise ValueError('RIL checkpoint does not match actual fixed inputs/generator')
    files = evidence['generation']['after']['files_sha256']
    if any(sha(ril / 'after' / n) != h for n, h in files.items()):
        raise ValueError('actual RIL generated inputs changed')
    header = (ril / 'after/ril/v1_5/iril_callback.h').read_text()
    if 'CMD_RIL_CALLBACK_COMMUNICATION_STATE_UPDATED = 162' not in header or 'CommunicationStateUpdated(' not in header:
        raise ValueError('new actual one-way RIL callback missing')
    overlay = [{'type': 'file', 'name': str(root / 'out/arm64_virt/gen/drivers/interface' / n),
                'external-contents': str(ril / 'after' / n), 'use-external-name': True}
               for n in files if n.endswith('.h')]
    script = 'build/templates/rust/rust_cxxbridge.py'
    tool = 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'
    for name in (script, tool):
        if sha(root / name) != data['frozen_other_inputs'][name]['sha256']:
            raise ValueError('actual fixed CXX generator differs')
    directory = output / 'generated-communication'
    directory.mkdir()
    cpp, hpp = directory / 'wrapper.rs.cc', directory / 'wrapper.rs.h'
    command = ['/usr/bin/env', str(root / script), '--cxxbridge', str(root / tool),
               '--cc', str(cpp), '--header', str(hpp), '--', str(staged / CXX)]
    with (output / 'cxxbridge-generate.log').open('xb') as log:
        subprocess.run(command, cwd=root / 'out/arm64_virt', stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    if 'on_communication_state_updated' not in hpp.read_text() or 'on_communication_state_updated' not in cpp.read_text():
        raise ValueError('actual regenerated CXX outputs omit the new communication state')
    old = root / 'out/arm64_virt/gen' / Path(CXX + '.h')
    overlay.append({'type': 'file', 'name': str(old), 'external-contents': str(hpp), 'use-external-name': True})
    generated_units = {'generated_wrapper': (root / 'out/arm64_virt/gen' / Path(CXX + '.cc'), cpp)}
    proof = {'scope': 'actual_fixed_cxxbridge_generation_and_prior_complete_real_RIL_HDI_checkpoint',
             'command': command, 'generator_sha256': sha(root / tool), 'driver_sha256': sha(root / script),
             'input_sha256': sha(staged / CXX), 'outputs_sha256': {str(p): sha(p) for p in (cpp, hpp)},
             'RIL_evidence_sha256': sha(ril / 'evidence.json'), 'RIL_after_files_sha256': files}
    return overlay, generated_units, proof
