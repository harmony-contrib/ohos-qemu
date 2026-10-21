"""Actual original Knowledge actor: retain raw cuts, keep its business calls.

The canonical CLI successor changes only its two producer imports to this
module. Its verifier still imports the original verify_hook. There is no
recorded-callback execution, new Collector, Guest or actor here.
"""
from pathlib import Path
from types import FunctionType
import json
import time

import apps_providers579_knowledge as original
from photos579_raw import need, ref
from photos579_project import sources

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/ci/capability-audit')
_installed = False
_base_bind = original.bind
_base_phase = original._after_phase
_base_cleanup = original.cleanup


def capture_bind(io):
    callbacks = _base_bind(io)
    state = {'case': None}
    if not hasattr(io, '_photos579_cuts'):
        io._photos579_cuts = []
    def wrapper(name):
        function = callbacks[name]
        def actual(*args):
            if name == 'prepare_callers': state['case'] = args[0]
            at, qt = len(io.receipts), len(io.qmp_receipts)
            ct = len(io.collector.value['commands'])
            cut = dict(schema='actual-photos579-callback-cut/v1', name=name, case=state['case'],
                args=list(args), boot_id=io.boot_id, archive_sha256=io.archive_sha256,
                before_monotonic_ns=time.monotonic_ns(), result=None, error=None)
            try:
                value = function(*args)
                cut['result'] = value
                return value
            except BaseException as error:
                cut['error'] = dict(type=type(error).__name__, message=str(error))
                raise
            finally:
                cut.update(after_monotonic_ns=time.monotonic_ns(),
                    commands=[io.ref_receipt(row) for row in io.receipts[at:]],
                    qmp_records=io.qmp_receipts[qt:],
                    collector_commands=io.collector.value['commands'][ct:])
                io._photos579_cuts.append(io._write('photos579_callback.json',
                    json.dumps(cut, ensure_ascii=False, indent=2)+'\n'))
        return actual
    return {name: wrapper(name) for name in callbacks}


def install():
    global _installed
    sources()
    need(Path(original.__file__).resolve() == ROOT/'apps_providers579_knowledge.py' and
        Path(_base_phase.__code__.co_filename).resolve() == Path(original.__file__),
        'actual original Knowledge implementation only')
    if _installed:
        return
    namespace = dict(_base_phase.__globals__)
    namespace['bind'] = capture_bind
    need(all(namespace[key] is value for key,value in _base_phase.__globals__.items()
        if key != 'bind'), 'all original business dependencies retained')
    replacement = FunctionType(_base_phase.__code__, namespace, _base_phase.__name__,
        _base_phase.__defaults__, _base_phase.__closure__)
    replacement.__kwdefaults__ = _base_phase.__kwdefaults__
    # Original after_phase calls this exact original body, with only the bind
    # dependency retaining additional actual calls. No return is synthesized.
    original._after_phase = replacement
    _installed = True


def retain(collector, phase):
    if not hasattr(collector, '_apps579_io'):
        return
    io = collector._apps579_io
    value = dict(schema='actual-photos579-original-collector-retention/v1',
        phase=phase, boot_id=io.boot_id, archive_sha256=io.archive_sha256,
        run_id=io.run_id, udid=io.udid, target=io.target,
        commands=io.receipts, qmp_records=io.qmp_receipts,
        callback_cuts=list(io._photos579_cuts),
        original_commands=collector.value['commands'],
        source=ref(Path(__file__).resolve()))
    actual = io._write('photos579_retention_'+phase+'.json',
        json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    collector.value.setdefault('photos579_raw_retention', []).append(actual)
    collector.persist()


def after_phase(collector, phase, artifacts):
    install()
    try:
        # The original wrapper records its original failure and cleanup.
        return original.after_phase(collector, phase, artifacts)
    finally:
        retain(collector, phase)


def cleanup(collector):
    install()
    try:
        return _base_cleanup(collector)
    finally:
        retain(collector, 'final_cleanup')
