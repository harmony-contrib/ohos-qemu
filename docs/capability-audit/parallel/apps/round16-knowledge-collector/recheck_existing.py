#!/usr/bin/env python3
"""Read existing SDK/helper artifacts only; no compiler, signer, HDC or VM."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'sdk-adapter', 'helper-build', 'helper-output', 'helper-frozen', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    dependency_root = args.repository.resolve() / 'ci/capability-audit'
    sys.path.insert(0, str(dependency_root))
    candidate = Path(__file__).resolve().parents[5] / 'ci/capability-audit/batch_media_knowledge_artifacts.py'
    spec = importlib.util.spec_from_file_location('candidate_knowledge_adapter', candidate)
    adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    # Rehearse the candidate after root cherry-pick. This selects the actual
    # root dependency file, then hashes it; no check or artifact is mocked.
    adapter.HERE = dependency_root
    sdk = adapter.load(args.sdk_adapter)
    helper = {'build': adapter.record(args.helper_build), 'output_directory': str(args.helper_output.resolve()),
              'path_map': {'/evidence/helpers': str(args.helper_output.resolve()), '/work': str(args.helper_frozen.resolve())}}
    value = dict(scope='actual_existing_receipts_readonly_NOT_compilation_signature_or_guest', candidate=adapter.record(candidate),
        dependency_context=str(dependency_root), source_receipt=adapter.record(args.sdk_adapter),
        note='HERE selects real root dependency location for post-cherry-pick rehearsal; receipts and validators unchanged.',
        projects={}, failures=[])
    for role, item in sdk['projects'].items():
        try: value['projects'][role] = adapter.project_binding(item, role, adapter.checked(sdk['challenge']))
        except Exception as error: value['failures'].append(role + ': ' + str(error))
    try: value['helper'] = adapter.helper_binding(helper)
    except Exception as error: value['failures'].append('helper: ' + str(error))
    value['status'] = 'pass_existing_receipts_ONLY' if not value['failures'] else 'fail'
    with args.output.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')
    print(json.dumps({'status': value['status'], 'projects': list(value['projects']), 'failures': value['failures']}))
    return int(bool(value['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
