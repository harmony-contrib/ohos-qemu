"""Exact source admission only; no native callback or runtime verdict."""
from pathlib import Path
import argparse
import hashlib
import json
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
COMPONENT = Path(__file__).resolve().parent
PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
FILES = (('frameworks/native/appkit/app/main_thread.cpp', '3680fd9fb200b103a87bc01d530e0c68deadfac843825354adb4182763618c1e', 'ed25c0dd5459e94c802aa9abcfb70baa3aba8110ae8b1f4a4f2ffd0bdb3b4528'),)
EXPECTED = {'schema': 'number_identity_native_trace495/v1', 'project': 'foundation/ability/ability_runtime', 'revision': '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8', 'files': [['frameworks/native/appkit/app/main_thread.cpp', '3680fd9fb200b103a87bc01d530e0c68deadfac843825354adb4182763618c1e', 'ed25c0dd5459e94c802aa9abcfb70baa3aba8110ae8b1f4a4f2ffd0bdb3b4528']], 'patch': '0001-record-number-native-causal-observations.patch', 'patch_sha256': '0ba3cd951c143aeb67fa181160981267949b4daf00f51559687792f47f6ecde8', 'source_only': True, 'build_or_guest_pass': False}

def metadata():
    raw = (COMPONENT / 'source_states.json').read_bytes()
    def unique(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate component metadata key')
            result[key] = value
        return result
    if (COMPONENT / 'source_states.json').is_symlink() or json.loads(raw, object_pairs_hook=unique) != EXPECTED:
        raise ValueError('exact diagnostic component metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches) != 1 or patches[0].name != EXPECTED['patch'] or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest() != EXPECTED['patch_sha256']:
        raise ValueError('exact diagnostic patch differs')

def validate(root, require_patched=False):
    metadata()
    root = Path(root).resolve()
    for relative, original, repaired in FILES:
        target = root / PROJECT / relative
        if target.is_symlink():
            raise ValueError('diagnostic source alias refused')
        if target.exists():
            info = target.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('single regular diagnostic source inode required')
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


OLD_ORIGINAL = 'ea42b93089e536e6ac8fea3dacadea9f3c93ca5fe0edd67f39cdc83a5bef2b2c'
OLD_COMPONENT = 'common/foundation/ability/ability_runtime/number_identity_loader'
A_COMPONENT = 'common/foundation/ability/ability_runtime/number_identity_native_trace495'
B_COMPONENT = 'common/base/telephony/number_identity/native_observation495'
OLD_GUARD_SHA = 'b598dfdfd78b245b827ebeafb33672291230d9942c29e7d22670122b3e840812'
B_GUARD_SHA = 'b6af1b69a9a75dfe3fc0b5d5575a6362d00c840b27cf0cd5749f7b9b5e49d537'

def _fixed_guard(relative, expected_sha, name):
    import importlib.util
    patch_root = COMPONENT.parents[4]
    path = patch_root / relative / 'verify_source.py'
    cursor = path
    while cursor != patch_root:
        if cursor.is_symlink():
            raise ValueError('fixed sequence guard alias refused')
        cursor = cursor.parent
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError('fixed sequence source guard identity differs')
    spec = importlib.util.spec_from_file_location(name, path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.metadata()
    return guard

def preflight_sequence(root, require_patched=False):
    """Pure complete-vector admission/plan; never apply, skip gates, or own resources."""
    metadata()
    root = Path(root).resolve()
    old = _fixed_guard(OLD_COMPONENT, OLD_GUARD_SHA, 'number_old_loader495')
    other = _fixed_guard(B_COMPONENT, B_GUARD_SHA, 'number_native_provider495')
    b_final = other.validate(root)
    relative, loaded_sha, trace_sha = FILES[0]
    target = root / PROJECT / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('MainThread sequence source alias refused')
        cursor = cursor.parent
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('one regular MainThread source inode required')
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual == OLD_ORIGINAL:
        if old.validate(root) is not False:
            raise ValueError('exact original old-loader state required')
        a_state = 'old-original'
        plan = [OLD_COMPONENT, A_COMPONENT, B_COMPONENT]
    elif actual == loaded_sha:
        if old.validate(root, require_patched=True) is not True or validate(root) is not False:
            raise ValueError('exact loaded old-loader state required')
        a_state = 'old-loaded'
        plan = [A_COMPONENT, B_COMPONENT]
    elif actual == trace_sha:
        if validate(root, require_patched=True) is not True:
            raise ValueError('exact trace-final MainThread state required')
        a_state = 'trace-final'
        plan = [] if b_final else [B_COMPONENT]
    else:
        raise ValueError('unknown MainThread whole-sequence state; preserving all source')
    if b_final and a_state != 'trace-final':
        raise ValueError('provider-final with old MainThread sequence refused')
    whole_final = a_state == 'trace-final' and b_final
    if require_patched and not whole_final:
        raise ValueError('complete MainThread/provider final vector required')
    return dict(scope='exact whole Number diagnostic source sequence only',
        mainthread_state=a_state, provider_state='final' if b_final else 'before',
        component_sequence=plan, whole_final=whole_final,
        compiled=False, native_callback_proven=False, guest_pass=False)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--require-patched', action='store_true')
    parser.add_argument('--preflight-sequence', action='store_true', help='explicit whole-sequence mode; also the default CLI behavior')
    args = parser.parse_args(argv)
    print(json.dumps(preflight_sequence(args.source_root, args.require_patched)))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
