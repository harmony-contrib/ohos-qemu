"""Exact upstream parser fixtures; not device photographs or fabricated backend data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REVISION = '711db218c8d1c4d6546b28d8cf466059644dfa77'
FIXTURES = {
    'read_test.tiff': '96820b8102f948124649e7fa084c3cc496ede0b8245384158e22a509f762f655',
    'test_dng_mock.dng': '5e405ce567ff82f153089ff319da61c4dbdbac2375b87a3e57f4e6c2b2b56f16',
    'bird_8bit_I420_599x359_fps10.avif': '235db171644870d1114400f2aa5fd30cb4bb903276ba2cc2eefb7a3452f08bca',
}


def verify(directory):
    for name, expected in FIXTURES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('image metadata fixture changed: ' + name)
    return dict(FIXTURES)


def export(source, output):
    component = source / 'foundation/multimedia/image_framework'
    revision = subprocess.check_output(['git', '-C', str(component), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('unexpected image framework revision')
    directory = component / 'test/resource/image/images'
    verify(directory)
    output.mkdir(parents=True, exist_ok=False)
    for name in FIXTURES:
        shutil.copy2(directory / name, output / name)
    (output / 'provenance.json').write_text(json.dumps(dict(revision=revision, files=verify(output)), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.source_root, args.output)
