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


def openssl_public_includes(root, product):
    # Exactly the published libcrypto_shared public config, including its
    # generated configuration header. No arbitrary caller include paths.
    build_file = 'third_party/openssl/BUILD.gn'
    path = root / build_file
    raw = path.read_bytes()
    text = raw.decode()
    declarations = (
        'build_all_generated_path = "${target_out_dir}/build_all_generated"',
        'crypto_config_common_public_include_dirs = [\n  "include",\n  "${build_all_generated_path}/include",\n]',
        'config("crypto_config_public") {\n  include_dirs = crypto_config_common_public_include_dirs\n  libs = mingw32_libs\n}',
    )
    if any(text.count(value) != 1 for value in declarations):
        raise ValueError('fixed OpenSSL published public config required')
    generated = root / 'out' / product / 'obj/third_party/openssl/build_all_generated/include'
    if not (generated / 'openssl/configuration.h').is_file():
        raise ValueError('actual product OpenSSL generated configuration missing')
    directories = [root / 'third_party/openssl/include', generated]
    flags = [item for directory in directories for item in ('-I', str(directory))]
    return flags, {'build_file': build_file, 'build_file_sha256': hashlib.sha256(raw).hexdigest(),
        'public_config': 'crypto_config_public', 'include_dirs': [str(p) for p in directories],
        'generated_configuration_sha256': hashlib.sha256((generated / 'openssl/configuration.h').read_bytes()).hexdigest(),
        'scope': 'fixed_declared_public_config_and_existing_product_generated_header_NOT_fresh_GN_selection'}
