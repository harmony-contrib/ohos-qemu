"""Reproduce the official SDK native strip, preserving exact source ELF identity."""
import hashlib
from pathlib import Path
import subprocess
import tempfile


def processed_payload(source, strip, expected_source_sha256, expected_strip_sha256):
    source, strip = Path(source), Path(strip)
    if source.is_symlink() or not source.is_file() or not strip.is_file():
        raise ValueError('actual compiled child ELF and official SDK native strip required')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_source_sha256:
        raise ValueError('actual compiled child native input differs')
    if hashlib.sha256(strip.read_bytes()).hexdigest() != expected_strip_sha256:
        raise ValueError('official SDK native strip identity differs')
    with tempfile.TemporaryDirectory(prefix='child-native-strip-replay-') as temporary:
        processed = Path(temporary) / source.name
        processed.write_bytes(raw)
        # LLVM dispatches strip/objcopy behavior from argv[0]; preserve the
        # official llvm-strip invocation name even when it is a symlink.
        subprocess.run([str(strip.absolute()), str(processed)], check=True, capture_output=True)
        result = processed.read_bytes()
    if source.read_bytes() != raw:
        raise ValueError('compiled child native input changed during strip replay')
    return result


def parameter_matches(actual, expected):
    """param get emits one value with native trailing whitespace, never extra tokens."""
    return (type(actual) is str and type(expected) is str and
            len(expected.split()) == 1 and actual.split() == expected.split())
