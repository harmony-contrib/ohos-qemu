"""Exact Number permission-domain translation; source identity is not runtime proof."""
from pathlib import Path
import argparse
import hashlib
import json
import stat
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
FILES = (('frameworks/js/src/napi_number_identity.cpp', '28d6466d157bfdb3b115887bab861fa843a82bdc5b0216fbd80bf811217d5756', '36a024778c3057f8f3dbe7ad620e5e8446f47cfe718e71c2d0edf65a92a97582'),)
COMPONENT = Path(__file__).resolve().parent
PATCH = '0001-translate-number-permission-to-public-201.patch'
PATCH_SHA256 = '2aa384169123af2301a902f79d85e7a8d3c2d263b502d541f8ca2748073956ea'
SCHEMA = 'number-identity-public-permission580/v1'
FIXTURES = (('original', FILES[0][1], 30541), ('final', FILES[0][2], 30652))
MAX_BYTES = 1024 * 1024


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate Number permission component metadata key')
        value[key] = item
    return value


def _read(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('canonical unlinked Number permission source required')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
        raise ValueError('bounded one-link regular Number permission source required')
    value = path.read_bytes()
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if (len(value) != before.st_size or
            any(getattr(before, key) != getattr(after, key) for key in fields)):
        raise ValueError('Number permission source changed during byte read')
    return value


def metadata():
    value = json.loads(_read(COMPONENT / 'source_states.json'), object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite component metadata')))
    expected = dict(schema=SCHEMA, project=PROJECT, revision=REVISION,
        files=[list(item) for item in FILES], patch=PATCH,
        patch_sha256=PATCH_SHA256, source_only=True, build_or_guest_pass=False)
    if value != expected:
        raise ValueError('exact Number permission metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if (len(patches) != 1 or patches[0].name != PATCH or
            hashlib.sha256(_read(patches[0])).hexdigest() != PATCH_SHA256):
        raise ValueError('exact single Number permission patch required')
    expected_fixtures = set()
    for endpoint, digest, count in FIXTURES:
        path = COMPONENT / 'fixtures' / endpoint / PROJECT / FILES[0][0]
        data = _read(path)
        if (len(data) != count or hashlib.sha256(data).hexdigest() != digest or
                stat.S_IMODE(path.stat().st_mode) != 0o644):
            raise ValueError('complete Number permission fixture differs')
        expected_fixtures.add(path)
    actual_fixtures = {path for path in (COMPONENT / 'fixtures').rglob('*')
                       if path.is_file() or path.is_symlink()}
    if actual_fixtures != expected_fixtures:
        raise ValueError('unknown or missing Number permission fixture')
    return value


def validate(root, require_patched=False):
    metadata()
    root = Path(root)
    if (not root.is_absolute() or root.resolve() != root or not root.is_dir() or
            any(path.is_symlink() for path in (root, *root.parents))):
        raise ValueError('actual canonical source root required')
    source = root / PROJECT / FILES[0][0]
    original = _read(source)
    result = validate_component(root, PROJECT, REVISION, FILES, require_patched)
    if _read(source) != original:
        raise ValueError('actual Number permission source changed during validation')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args(argv)
    result = validate(args.source_root, args.require_patched)
    print(json.dumps({'scope': 'Number permission exact source component only',
        'patched': result, 'compiled': False, 'runtime_permission_validated': False,
        'aggregate_provider_passed': False, 'guest_pass': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
