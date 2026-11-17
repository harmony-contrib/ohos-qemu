#!/usr/bin/env python3
"""Independent PrivacyCenter staging/source verifier; shared build wiring is external."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from privacycenter_provider import main

if __name__ == '__main__': raise SystemExit(main())
