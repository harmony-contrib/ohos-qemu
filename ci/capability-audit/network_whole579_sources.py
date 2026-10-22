"""Finite normal peer source projection, not a resource or runtime producer.

Root calls materialize_peer_linux only during its normal source preparation.
The unchanged original base14/netlink15 historical locks remain read-only.
No old result/receipt is rewritten to assert a new SDK/native/runtime outcome.
"""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import json
import stat
from network_whole579_records import need, raw, doc, ref, save

HERE = Path(__file__).resolve().parent
RUNTIME = ('peer_lock.json', 'peer_linux_build.py', 'peer_server.py', 'linux_rtnetlink.py',
    'backend_proof.py', 'source_recipe.py', 'recipe-lock.json', 'configure-peer.patch',
    'peer_plan.py', 'frozen-base.json', 'frozen-netlink.json')


def materialize_peer_linux(output):
    """Return exact origin->actual source rows for the original normal projector.

    This function never edits Normal SOURCE, a capsule, a receipt, the active
    original peer actor map or another directory. Root must feed these rows to
    the finite normal Network/API projector, regenerate all active manifests,
    then use the actual normal SDK/peer production. This output alone cannot
    be selected as a peer runtime envelope.
    """
    spec = doc(ref(HERE / 'network_whole579/PEER-SOURCES.json'))
    need(spec['schema'] == 'network-whole579-normal-peer-source/v1' and
        tuple(row['relative'] for row in spec['files']) == RUNTIME and
        spec['actual_runtime'] is None, 'fixed eleven-file peer projection')
    output = Path(output)
    need(output.is_absolute() and output.resolve() == output and output.parent.is_dir() and
        not output.exists(), 'fresh explicit Root normal source output')
    # Verify the whole finite input vector before writing any output.
    inputs = []
    for row in spec['files']:
        before = raw(row['before']); after = raw(row['after'])
        need(row['relative'] in RUNTIME and (row['relative'] in ('peer_plan.py', 'peer_server.py', 'source_recipe.py') or before == after),
            'only three exact peer source deltas')
        inputs.append((row, after))
    output.mkdir(mode=0o700)
    rows = []
    for row, body in inputs:
        target = output / row['relative']
        with target.open('xb') as stream: stream.write(body)
        target.chmod(row['mode'])
        actual = ref(target)
        rows.append(dict(origin=row['before'], actual=dict(actual, bytes=len(body)), relative=row['relative'],
            mode=stat.S_IMODE(target.stat().st_mode)))
    vector = save(output / 'SOURCE-PROJECTION579.json', dict(schema='network-whole579-peer-source-projection/v1',
        fixed_source=ref(HERE / 'network_whole579/PEER-SOURCES.json'), files=rows, original_actor_count=2,
        original_protocol375_unchanged=True, original17_steps_unchanged=True,
        runtime_envelope=None, runtime_pass=False, first_artifact_behavior_gate_passed=False))
    return dict(source_projection=vector, peer_linux=str(output), files=rows,
        original_source_context_reprojection_required=True, actual_runtime=None)
