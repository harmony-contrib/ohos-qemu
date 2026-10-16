"""Read literal public GN include exports for labeled compile diagnostics only.

These are declared dependency exports, not a fresh GN graph. Original compiler
flags remain intact; the resulting proof must never be used as GN selection.
"""
import hashlib
from pathlib import Path
import re


def exported_includes(root, build_file, config):
    path = root / build_file
    raw = path.read_bytes()
    text = raw.decode()
    anchor = 'config("' + config + '") {'
    if text.count(anchor) != 1:
        raise ValueError('one fixed public GN config required')
    start = text.index(anchor) + len(anchor)
    depth, end = 1, start
    while depth:
        if end >= len(text):
            raise ValueError('unterminated GN config')
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    block = text[start:end - 1]
    arrays = re.findall(r'include_dirs\s*=\s*\[([^]]*)\]', block)
    if len(arrays) != 1:
        raise ValueError('literal public include_dirs array required')
    values = re.findall(r'"([^"\n]+)"', arrays[0])
    if not values or re.sub(r'"[^"\n]+"|[\s,]', '', arrays[0]):
        raise ValueError('nonliteral GN include export rejected')
    flags = []
    for value in values:
        if '$' in value or '..' in Path(value).parts:
            raise ValueError('dynamic GN include export needs fresh GN')
        resolved = root / value[2:] if value.startswith('//') else path.parent / value
        if not resolved.is_dir():
            raise ValueError('declared GN export directory missing: ' + str(resolved))
        flags += ['-I', str(resolved)]
    return flags, {'build_file': build_file, 'build_file_sha256': hashlib.sha256(raw).hexdigest(),
        'public_config': config, 'literal_include_dirs': values,
        'scope': 'declared_public_config_exports_ONLY_NOT_fresh_GN_dependency_selection'}
