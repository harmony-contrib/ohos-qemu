#!/usr/bin/env python3
"""Prepare only this fixed source vector in the actual product build."""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
PATCHES = next(p for p in HERE.parents if p.name == 'patches')
sys.path.insert(0, str(PATCHES / 'lib'))
from guarded_source_vector579 import main
if __name__ == '__main__':
    sys.argv[1:1] = ['--component-dir', str(HERE)]
    main()
