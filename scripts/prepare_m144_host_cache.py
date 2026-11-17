#!/usr/bin/env python3
"""Prepare OHPM's existing cache path without replacing HOME or cache aliases."""
import json
from pathlib import Path
import tempfile


def prepare_cache(home):
    home = Path(home)
    if not home.is_absolute() or not home.is_dir():
        raise ValueError('M144 host home must already be an absolute directory')
    cache = home / '.ohpm'
    alias = cache.readlink() if cache.is_symlink() else None
    target = cache.resolve()
    # Prepared OHOS images can contain a cache alias whose target was only
    # mounted by the OS builder. Create that cache directory in this private
    # container; never remove/replace the alias or populate a broad directory.
    if target.is_symlink() or target.name != '.ohpm' or target == home.resolve():
        raise ValueError('OHPM cache alias does not identify a .ohpm cache directory')
    if target.exists() and not target.is_dir():
        raise ValueError('OHPM cache target is not a directory')
    existed = target.is_dir()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(prefix='m144-cache-write-check-', dir=cache) as stream:
        stream.write(b'OHPM cache preparation\n')
        stream.flush()
    if alias is not None and (not cache.is_symlink() or cache.readlink() != alias):
        raise ValueError('OHPM cache alias changed during preparation')
    return {'scope': 'container_OHPM_cache_bootstrap_NOT_HAP_or_guest_acceptance',
            'home': str(home), 'cache': str(cache), 'target': str(target),
            'preserved_alias': str(alias) if alias is not None else None,
            'target_preexisted': existed, 'cache_writable': True}


if __name__ == '__main__':
    print(json.dumps(prepare_cache(Path.home()), sort_keys=True))
