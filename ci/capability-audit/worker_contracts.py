"""One explicit Worker version per fresh app; exact generated source contracts."""
import hashlib
from pathlib import Path
import re

MODES = {'legacy': ('Worker', 'parentPort', 'workerPort', 'MessageEvent', 0),
         'thread': ('ThreadWorker', 'workerPort', 'parentPort', 'MessageEvents', 10200004)}
DESTINATIONS = {'worker_host_probe.ets': 'entry/src/main/ets/pages/Index.ets',
                'worker_thread_probe.ets': 'entry/src/main/ets/workers/ApiWorker.ets'}
HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def generated(mode, run_id):
    if mode not in MODES or re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('explicit single Worker version and fresh challenge required')
    constructor, port, other_port, event, error_code = MODES[mode]
    substitutions = {'__RUN__': run_id, '__MODE__': mode, '__CLASS__': constructor,
        '__PORT__': port, '__OTHER_PORT__': other_port, '__EVENT__': event,
        '__HOST_EVENT__': 'MessageEvent<Reply>' if mode == 'legacy' else 'MessageEvents',
        '__WORKER_EVENT__': 'MessageEvent<Request>' if mode == 'legacy' else 'MessageEvents',
        '__POST_EXIT_CODE__': str(error_code)}
    sources, hashes = {}, {}
    for template_name, destination in DESTINATIONS.items():
        original = (HERE / template_name).read_bytes()
        content = original.decode()
        for old, new in substitutions.items():
            content = content.replace(old, new)
        sources[destination] = content
        hashes[template_name] = digest(original)
        hashes[destination] = digest(content.encode())
    return sources, hashes


def verify_inputs(document, project, run_id, arch, mode):
    constructor, port, _, _, _ = MODES[mode]
    if (document.get('schema_version') != 1 or document.get('run_id') != run_id or document.get('arch') != arch or
            arch not in ('arm64', 'armv7a', 'x86_64') or document.get('role') != 'ordinary_app' or
            document.get('mode') != mode or document.get('worker_class') != constructor or document.get('port_name') != port or
            document.get('scope') != 'worker_context_ports_and_transfer_lifecycle_only'):
        raise ValueError('Worker compiled caller identity/scope mismatch')
    sources, hashes = generated(mode, run_id)
    if document.get('source_sha256') != hashes:
        raise ValueError('Worker templates or compiled source differ from the exact current contract')
    for relative, expected in sources.items():
        path = project / relative
        cursor = path
        while cursor != project:
            if cursor.is_symlink():
                raise ValueError('Worker compiled source contains an alias')
            cursor = cursor.parent
        if path.read_text() != expected:
            raise ValueError('Worker source differs from its actual challenge-bound caller')
    declaration = Path(document.get('sdk_worker_declaration', ''))
    if (not declaration.is_file() or declaration.is_symlink() or
            digest(declaration.read_bytes()) != document.get('sdk_worker_declaration_sha256')):
        raise ValueError('Worker SDK declaration changed after compilation')
    return hashes
