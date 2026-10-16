"""Apply real runtime patches to fixed-source slices before host function execution."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/location/location/api26_runtime'
FIXTURE = Path(__file__).parent / 'fixtures/batch_location/location_runtime_before.json'
PREFIX = 'base/location/location/'


def runtime_sources(prefix=None):
    files = json.loads(FIXTURE.read_text())['files']
    with tempfile.TemporaryDirectory(prefix='batch-location-fixed-slices-') as directory:
        source = Path(directory)
        for name, text in files.items():
            target = source / (PREFIX + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if text is not None:
                target.write_text(text)
        patches = sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
        for patch in patches if prefix is None else patches[:prefix]:
            subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True, capture_output=True)
        return {name: (source / (PREFIX + name)).read_text() if (source / (PREFIX + name)).exists() else None for name in files}


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1] + '\n'
    raise AssertionError(signature)
