#!/usr/bin/env python3
"""Read-only audit of tracked ArkWeb include references, NOT an active-feature proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]+"(arkweb/[^"\n]+)"', re.MULTILINE)


def references(text):
    lines = text.splitlines()
    records = []
    for match in INCLUDE.finditer(text):
        line = text[:match.start()].count('\n') + 1
        records.append({'include': match[1], 'line': line,
                        'preceding_context': lines[max(0, line - 9):line - 1]})
    return records


def audit(source, generated_roots=()):
    roots = [('chromium', source), ('arkweb', source / 'arkweb'), ('cef', source / 'cef')]
    result = {'scope': 'tracked_source_ArkWeb_include_presence_NOT_full_include_graph_or_active_feature_validation',
              'first_artifact_behavior_gate_passed': False, 'missing_references': [], 'repositories': {},
              'real_generated_search_roots': [str(path) for path in generated_roots], 'generated_headers_sha256': {}}
    for name, root in roots:
        head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        files = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--', '*.cc', '*.cpp', '*.h', '*.hpp'])
        checked = references_count = 0
        referenced_files = {}
        for filename in files.decode().split('\0'):
            if not filename:
                continue
            path = root / filename
            if not path.is_file():
                continue  # Deleted tracked files are not compilation inputs.
            raw = path.read_bytes()
            if b'arkweb/' not in raw:
                continue
            checked += 1
            found = references(raw.decode('utf-8', errors='replace'))
            if not found:
                continue
            referenced_files[filename] = hashlib.sha256(raw).hexdigest()
            references_count += len(found)
            for record in found:
                target = source / record['include']
                generated = next((directory / record['include'] for directory in generated_roots
                                  if (directory / record['include']).is_file()), None)
                if not target.is_file() and generated is not None:
                    result['generated_headers_sha256'][str(generated)] = hashlib.sha256(generated.read_bytes()).hexdigest()
                elif not target.is_file():
                    result['missing_references'].append({'repository': name, 'source': filename,
                        'source_sha256': referenced_files[filename], **record,
                        'active_feature': 'unknown_requires_real_GN_and_preprocessor_check'})
        result['repositories'][name] = {'revision': head, 'matching_files_scanned': checked,
                                       'references': references_count, 'source_files_sha256': referenced_files}
    result['missing_count'] = len(result['missing_references'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated-root', type=Path, action='append', default=[],
                        help='real native GN gen include directory; generated headers are not source omissions')
    args = parser.parse_args()
    source = args.source_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('source must be read-only')
    if args.output.exists():
        raise ValueError('refusing to overwrite prior include audit')
    generated = [path.resolve() for path in args.generated_root]
    if any(not path.is_dir() or not path.is_relative_to(source) for path in generated):
        raise ValueError('generated search roots must be actual directories inside the read-only source tree')
    script_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result = audit(source, generated)
    result['auditor_sha256'] = script_sha256
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'missing_count': result['missing_count'], 'active_features_validated': False,
                      'first_artifact_behavior_gate_passed': False}))
