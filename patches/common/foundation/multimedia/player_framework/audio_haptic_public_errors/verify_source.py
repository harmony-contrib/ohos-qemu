#!/usr/bin/env python3
import argparse
from pathlib import Path
from install import state
p = argparse.ArgumentParser()
p.add_argument('--source-root', type=Path, required=True)
p.add_argument('--require-patched', action='store_true')
a = p.parse_args()
print(state(a.source_root, a.require_patched))
