"""Fixed Photos source admission and held-main seam; no new resource owner.

The selected public implementation is the immutable true2in1 Photos capsule.
Ordinary source assembly may call source_rows(snapshot); the original main
calls install only after the original Knowledge wrapper has been installed.
This module never calls a business decoder or makes an acceptance decision.
"""
from pathlib import Path
import hashlib
import json
import stat

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = ROOT / '.tmp/parallel-capability-20261016'
CANONICAL = ROOT / 'ci/capability-audit'
CAPSULE = H / 'root-normal-link579-private-source-successors/photos'
FROZEN_SHA = 'b07ae6448fe854215948cc9bacbc4a0eefa26cab8d5a5ea98c71edc7197cace0'
PINS_SHA = 'e5863a8463a72243c1f7928c1db4853b21824e965762b9e8ef160e17a80a32e6'
MIGRATION_SHA = 'e01942f67dc8ff68514ef50c6aabfa1917e1b15d7f2decd3c3a8031c88eb2f79'
_installed = False


def need(ok, message):
    if not ok:
        raise ValueError(message)


def record(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
        not any(p.is_symlink() for p in (path, *path.parents)), 'fixed regular Photos source')
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def checked(row):
    need(type(row) is dict and set(row) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}),
        'source Ref2/3 only')
    path = Path(row['path'])
    need(record(path) == {key: row[key] for key in ('path', 'sha256')} and
        ('bytes' not in row or path.stat().st_size == row['bytes']), 'changed fixed Photos source')
    return path


def read(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'duplicate Photos source key')
            value[key] = item
        return value
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite source DATA')))


def source_rows(snapshot=None):
    """Read the fixed complete source closure; never refresh an expected SHA.

    snapshot is the actual new Kit's complete canonical snapshot. All canonical
    source rows, including the original two-line Knowledge CLI successor, must
    already be in that snapshot. A changed dependency requires a separately
    reviewed source successor; it is never silently rebound by this function.
    """
    rows = {}
    def add(row):
        path = checked(row)
        item = record(path)
        need(str(path) not in rows or rows[str(path)] == item, 'conflicting fixed Photos source')
        rows[str(path)] = item
        return path
    marker = add(dict(path=str(CAPSULE / 'FROZEN.json'), sha256=FROZEN_SHA))
    frozen = read(marker)
    need(frozen['schema'] == 'photos579-true2in1-source-candidate-frozen/v1' and
        len(frozen['members']) == 65 and frozen['source_commit'] is None and
        frozen['kit'] is None and frozen['normal_source'] is None,
        'complete immutable Photos source-only preimage')
    names = {str(marker)}
    for row in frozen['members']:
        name = Path(row['path'])
        need(not name.is_absolute() and '..' not in name.parts and name.as_posix() == row['path'],
            'finite physical Photos member')
        path = CAPSULE / name
        need(str(path) not in names, 'duplicate physical Photos member')
        add(dict(path=str(path), sha256=row['sha256'], bytes=row['bytes']))
        need(stat.S_IMODE(path.stat().st_mode) == row['mode'], 'physical Photos source mode differs')
        names.add(str(path))
    need({str(p) for p in CAPSULE.rglob('*') if p.is_file() or p.is_symlink()} == names,
        'unlisted Photos source, alias or cache')
    pins = read(add(dict(path=str(CAPSULE / 'SOURCE-PINS.json'), sha256=PINS_SHA)))
    need(pins['schema'] == 'photos579-2in1-fixed-source-inputs/v1', 'fixed complete Photos source inputs')
    for row in pins['files']:
        add(row)
    migration = read(add(dict(path=str(CAPSULE / 'MIGRATION.json'), sha256=MIGRATION_SHA)))
    need(migration['schema'] == 'photos579-finite-source-migration/v1' and
        len(migration['changes']) == 17, 'complete Photos17 source adoption required')
    for row in migration['changes']:
        target, payload = Path(row['target']), checked({key: row['after'][key] for key in ('path', 'sha256', 'bytes')})
        need(target.is_relative_to(CANONICAL) and
            (target.name.startswith('photos579_') or target.parent == CANONICAL / 'photos579' or
             target == CANONICAL / 'batch_media_knowledge_suite.py'), 'only finite Photos source destinations')
        add(dict(path=str(target), sha256=row['after']['sha256'], bytes=row['after']['bytes']))
        need(target.read_bytes() == payload.read_bytes() and
            stat.S_IMODE(target.stat().st_mode) == row['after']['mode'], 'Photos source adoption differs')
    own = add(record(CANONICAL / 'photos579_root_integration.py'))
    need(own == Path(__file__).resolve(), 'one fixed canonical integration source')
    if snapshot is not None:
        document = read(checked(snapshot))
        need(document['source_commit'] != '72d4d45b6d52955ab8b2c6b6cf9993c50775e019' and
            document['count'] == len(document['files']), 'actual new complete canonical source snapshot')
        canonical = {str(ROOT / row['path']): row for row in document['files']}
        need(len(canonical) == document['count'], 'unique full canonical snapshot')
        for path, row in rows.items():
            target = Path(path)
            if target.is_relative_to(ROOT) and not target.is_relative_to(H):
                need(path in canonical and canonical[path]['sha256'] == row['sha256'] and
                    canonical[path]['bytes'] == target.stat().st_size and
                    canonical[path]['mode'] == stat.S_IMODE(target.stat().st_mode),
                    'Photos canonical source missing from actual new snapshot')
    return [rows[name] for name in sorted(rows)]


def install(children, *, knowledge_install):
    """One wrapper, after original Knowledge and before Calendar/API sealing.

    Fixed Root code passes the actual just-called Knowledge installer. Runtime
    DATA cannot select that callable, module, a bundle or a verifier.
    """
    global _installed
    need(not _installed and Path(__file__).resolve() == CANONICAL / 'photos579_root_integration.py',
        'one fixed Photos integration install')
    own = record(Path(__file__).resolve())
    need(children.policy.sources.get(own['path']) == own['sha256'],
        'Root new Kit must explicitly admit the fixed integration source first')
    rows = source_rows()
    for row in rows:
        path = Path(row['path'])
        previous = children.policy.sources.get(row['path'])
        if path.is_relative_to(ROOT) and not path.is_relative_to(H):
            need(previous == row['sha256'], 'Root new Kit must explicitly admit each canonical Photos source')
        need(previous is None or previous == row['sha256'], 'conflicting actual source admission')
        children.policy.sources[row['path']] = row['sha256']
    import capability578_stage as canonical
    import photos579_stage as photos
    need(Path(canonical.__file__).resolve() == CANONICAL / 'capability578_stage.py' and
        Path(photos.__file__).resolve() == CANONICAL / 'photos579_stage.py', 'fixed canonical modules only')
    previous = canonical.run_on_owner
    knowledge_path = Path(knowledge_install.__code__.co_filename).resolve()
    need(knowledge_install.__name__ == 'install' and knowledge_path.name == 'knowledge579_stage.py' and
        children.policy.sources.get(str(knowledge_path)) == record(knowledge_path)['sha256'] and
        Path(previous.__code__.co_filename).resolve() == knowledge_path and
        previous.__name__ == 'original_then_knowledge', 'actual already-installed original Knowledge wrapper')
    photos.install_true2in1_preparation()
    def original_then_photos(owner, inputs_ref, resources, **context):
        result = previous(owner, inputs_ref, resources, **context)
        photos.run_after_knowledge(owner, resources, inputs_ref, **context)
        return result
    canonical.run_on_owner = original_then_photos
    _installed = True
