"""Original primary readonly export followed by optional bounded source facts."""
from pathlib import Path
import hashlib
import json
import runpy
import sys


def record(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)


# Primary errors always propagate. This call preserves original argv, source,
# readonly guards and outputs; the optional fact source never replaces them.
runpy.run_path('/evidence/inner.py', run_name='__main__')
output = Path('/evidence')
targets = (output / 'native-export/installed-runtime-export.json', output / 'export.json')
report = dict(schema='optional-six-source-stage579/v1', status='not_started',
    original_manifests_before=[record(path) for path in targets], runtime_pass=False,
    first_artifact_behavior_gate_passed=False)
try:
    folder = output / 'six-source-payload579'
    expected = {
        'six_source_export579.py': 'c63a2cb85b393288804807503f8f9654376e563e3211c2f151a1420a74a0c850',
        'six_source_request579.py': '051216eb36317d04ecd9226b6fc9a3f6ad4a22c311ea64a2bc4655690d0694e3',
    }
    report['sources'] = [record(folder / name) for name in expected]
    for row in report['sources']:
        if row['sha256'] != expected[Path(row['path']).name]:
            raise ValueError('fixed optional source bytes changed before import')
    sys.path.insert(0, str(folder))
    from six_source_export579 import append_facts
    report['result'] = append_facts()
    report['status'] = 'optional_source_collection_returned'
except Exception as error:
    report.update(status='optional_source_collection_failed', error=type(error).__name__ + ': ' + str(error))
finally:
    report['original_manifests_after'] = [record(path) for path in targets]
    report['original_manifests_unchanged'] = report['original_manifests_before'] == report['original_manifests_after']
    (output / 'six-source-stage579.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['original_manifests_unchanged']:
        raise ValueError('optional source collection changed the original primary export')

# This is the same already-owned readonly export CID. Retain current source
# identities for the narrowly adopted RTT/OOB source scope without a second
# resource owner or any runtime verdict.
rtt = dict(schema='optional-rtt-source-stage579/v1', status='not_started',
    original_manifests_before=[record(path) for path in targets], runtime_pass=False,
    first_artifact_behavior_gate_passed=False)
try:
    source = output / 'rtt-source-payload579/append_rtt579_source_facts.py'
    rtt['source'] = record(source)
    if rtt['source']['sha256'] != 'ede974d47c43d56e656b42673ddb5b810efacaa4e3cb3efb424acdf9f6b6557d':
        raise ValueError('fixed RTT readonly source payload changed')
    sys.path.insert(0, str(source.parent))
    from append_rtt579_source_facts import append_rtt_facts
    rtt['result'] = append_rtt_facts(source_root=Path('/ohos'),
                                   output=output / 'rtt-source-facts579')
    rtt['status'] = 'optional_source_collection_returned'
except Exception as error:
    rtt.update(status='optional_source_collection_failed', error=type(error).__name__ + ': ' + str(error))
finally:
    rtt['original_manifests_after'] = [record(path) for path in targets]
    rtt['original_manifests_unchanged'] = rtt['original_manifests_before'] == rtt['original_manifests_after']
    (output / 'rtt-source-stage579.json').write_text(json.dumps(rtt, indent=2) + '\n')
    if not rtt['original_manifests_unchanged']:
        raise ValueError('RTT source collection changed the original primary export')

# Fixed Media product facts in this SAME original readonly export CID. The
# original primary/six-source/RTT code and output guards above stay intact.
media = dict(schema='media-product-source-stage579/v1', status='not_started',
    original_manifests_before=[record(path) for path in targets], runtime_pass=False,
    first_artifact_behavior_gate_passed=False)
try:
    folder = output / 'media-source-payload579'
    expected = {'export_media579_source.py': 'b6da8f2751db987ba72a3ff49eecc80a228898e97f12ac62c301ff29471c02e1', 'media579_source_request.py': 'e2058f3a9b7374b77371900da031111dd698d4729fd1550a9e4f6d2edd43df88'}
    media['sources'] = [record(folder / name) for name in expected]
    for row in media['sources']:
        if row['sha256'] != expected[Path(row['path']).name]:
            raise ValueError('fixed Media readonly source payload changed')
    for name in ('media579_source_request', 'export_media579_source'):
        previous = sys.modules.get(name)
        if previous is not None and Path(previous.__file__).resolve() != folder / (name + '.py'):
            raise ValueError('foreign cached Media collector source')
    sys.path.insert(0, str(folder))
    from export_media579_source import append_media_facts
    media['result'] = append_media_facts()
    if any(record(folder / name)['sha256'] != digest for name, digest in expected.items()):
        raise ValueError('fixed Media source changed during actual export')
    media['status'] = 'media_source_collection_returned'
except Exception as error:
    media.update(status='media_source_collection_failed', error=type(error).__name__ + ': ' + str(error))
finally:
    media['original_manifests_after'] = [record(path) for path in targets]
    media['original_manifests_unchanged'] = media['original_manifests_before'] == media['original_manifests_after']
    (output / 'media-source-stage579.json').write_text(json.dumps(media, indent=2) + '\n')
    if not media['original_manifests_unchanged']:
        raise ValueError('Media source collection changed the original primary export')
