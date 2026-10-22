"""Small pure file primitives; producers do not import the private final actor."""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import hashlib
import json
import stat


def need(ok, message):
    if not ok: raise ValueError(message)


def loads(body):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            need(k not in out, 'duplicate raw JSON key'); out[k] = v
        return out
    return json.loads(body, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def regular(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary absolute immutable file')
    before = path.stat(); need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 1024**3, 'bounded complete regular bytes')
    body = path.read_bytes(); after = path.stat()
    need(all(getattr(before, k) == getattr(after, k) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')), 'file changed during read')
    return body


def ref(path):
    return {'path': str(path), 'sha256': hashlib.sha256(regular(path)).hexdigest()}


def raw(value):
    need(type(value) is dict and set(value) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}), 'exact actual Ref2/3')
    body = regular(value['path'])
    need(hashlib.sha256(body).hexdigest() == value['sha256'] and ('bytes' not in value or len(body) == value['bytes']), 'actual raw bytes/SHA')
    return body


def doc(value): return loads(raw(value))


def save(path, value):
    path = Path(path)
    need(path.is_absolute() and path.parent.resolve() == path.parent and path.parent.is_dir(), 'actual fixed output parent')
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    return ref(path)
