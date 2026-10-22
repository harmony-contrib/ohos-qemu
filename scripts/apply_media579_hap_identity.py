#!/usr/bin/env python3
"""Apply the exact RO20 audio permission successor in normal product source.

Only two unconditional root-build HAP bypasses are removed. Actual complete
source bytes are transformed by fixed unique cuts, then compared to the fixed
new asset. Native/shell/explicit UID_ROOT routes and all other source remain.
This is source preparation only; it never grants, retags or alters a binary.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import stat
import tempfile

TARGET = 'foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_utils.cpp'
BEFORE = 'b26daaab04c8379c8ab8a3838c95e000154979e056eb402d7e79132ff0dcd592'
AFTER = '64548d0ef53c475ff90d62627b75ceea16f392d74f00253d8baa1da925253c1d'
REVIEWED_AUDIO_HEAD = '6932fa64335b8272ca4a59de7808ab0d6c9eae7a'
CUTS = ({'before': 'bool PermissionUtil::VerifyIsSystemApp()\n{\n#ifdef AUDIO_BUILD_VARIANT_ROOT\n    return true;\n#endif\n    uint64_t fullTokenId = IPCSkeleton::GetCallingFullTokenID();', 'after': 'bool PermissionUtil::VerifyIsSystemApp()\n{\n    uint64_t fullTokenId = IPCSkeleton::GetCallingFullTokenID();'}, {'before': 'bool PermissionUtil::VerifySelfPermission()\n{\n#ifdef AUDIO_BUILD_VARIANT_ROOT\n    return true;\n#endif\n    Security::AccessToken::FullTokenID selfToken = IPCSkeleton::GetSelfTokenID();', 'after': 'bool PermissionUtil::VerifySelfPermission()\n{\n    Security::AccessToken::FullTokenID selfToken = IPCSkeleton::GetSelfTokenID();'})
LIMIT = 2 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def need(value, message):
    if not value:
        raise ValueError(message)


def identity(value):
    return tuple(getattr(value, key) for key in
        ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read_regular(path):
    path = Path(path)
    need(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
        'exact nonlinked normal source/asset path required')
    prior = path.lstat()
    need(stat.S_ISREG(prior.st_mode) and prior.st_size <= LIMIT, 'bounded complete regular source required')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(LIMIT + 1)
        closed = os.fstat(stream.fileno())
    need(len(raw) == prior.st_size and identity(prior) == identity(opened) == identity(closed) == identity(path.lstat()),
        'complete source changed during read')
    return raw, prior


def transform(raw, *, inverse=False):
    need(digest(raw) == (AFTER if inverse else BEFORE), 'one exact reviewed complete source vector required')
    for cut in (reversed(CUTS) if inverse else CUTS):
        old, new = (cut['after'], cut['before']) if inverse else (cut['before'], cut['after'])
        old, new = old.encode(), new.encode()
        need(raw.count(old) == 1, 'one unique reviewed permission function cut required')
        raw = raw.replace(old, new, 1)
    need(digest(raw) == (BEFORE if inverse else AFTER), 'finite permission cuts differ from complete reviewed successor')
    return raw


def apply(root, receipt):
    root = Path(root)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and root != Path('/'), 'actual normal source root required')
    target = root / TARGET
    asset = Path(__file__).resolve().parent / 'media579-product/audio_utils.cpp'
    asset_raw, asset_state = read_regular(asset)
    need(digest(asset_raw) == AFTER, 'exact new complete normal permission asset required')
    transform(asset_raw, inverse=True)
    original, original_state = read_regular(target)
    current = digest(original)
    need(current in (BEFORE, AFTER), 'foreign complete audio permission source preimage')
    desired = transform(original) if current == BEFORE else original
    need(desired == asset_raw, 'actual finite-cut result must equal every byte of new asset')
    if current == AFTER:
        transform(original, inverse=True)
    else:
        fd, name = tempfile.mkstemp(prefix=target.name + '.media579.', dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(desired)
                state = os.fstat(stream.fileno())
                if (state.st_uid, state.st_gid) != (original_state.st_uid, original_state.st_gid):
                    os.fchown(stream.fileno(), original_state.st_uid, original_state.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(original_state.st_mode))
                stream.flush()
                os.fsync(stream.fileno())
            prepared, prepared_state = read_regular(temporary)
            need(prepared == desired, 'complete staged permission source differs')
            now, now_state = read_regular(target)
            need(now == original and identity(now_state) == identity(original_state), 'actual source preimage changed before publication')
            again, again_state = read_regular(asset)
            need(again == asset_raw and identity(again_state) == identity(asset_state), 'fixed normal asset changed before publication')
            os.replace(temporary, target)
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()
    final, final_state = read_regular(target)
    need(final == desired and digest(final) == AFTER and
        (stat.S_IMODE(final_state.st_mode), final_state.st_uid, final_state.st_gid) ==
        (stat.S_IMODE(original_state.st_mode), original_state.st_uid, original_state.st_gid),
        'actual full-token HAP source/ownership write mismatch')
    receipt = Path(receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(dict(schema='media579-normal-source-HAP-identity-apply/v1', path=TARGET,
        before=BEFORE, after=AFTER, actual_preimage_sha256=current, was_already_applied=current == AFTER,
        transformation='two fixed unique permission-function cuts on the complete actual RO20 source',
        reviewed_preimage_audio_head=REVIEWED_AUDIO_HEAD, source_only=True, runtime_pass=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    apply(args.source_root, args.receipt)
