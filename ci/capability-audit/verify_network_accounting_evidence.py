"""Replay archive-bound ordinary network accounting evidence for delivery."""
import json
from pathlib import Path

from network_accounting_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
import verify_network_accounting_results as verifier


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('persona') != 'network-accounting' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('network accounting belongs to another package, boot, role or ABI')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit network accounting result required')
    root = result_path.parent
    files = dict(result=result_path, raw_results=root / 'results.log',
        ordinary_identity=root / 'application-identity.json', hap=root / 'ordinary-probe-signed.hap',
        compiled_contract_inputs=root / 'project/network-accounting-probe-inputs.json',
        http_peer=root / 'http-peer.json')
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual network accounting evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(verifier.__file__))):
        raise ValueError('network accounting summary is stale or belongs to another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs'), ('http_peer_sha256', 'http_peer')):
        if value.get(field) != digest(files[key]):
            raise ValueError('network verifier did not consume captured evidence: ' + key)
    inputs = json.loads(files['compiled_contract_inputs'].read_text())
    verify_inputs(inputs, document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verifier.verify(files['raw_results'].read_text(), document['run_id'], identity,
                             json.loads(files['http_peer'].read_text()), inputs['endpoint'])
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('network summary differs from raw ordinary-app observations')
    return actual
