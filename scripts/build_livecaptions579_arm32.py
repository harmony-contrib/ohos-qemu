#!/usr/bin/env python3
"""Normal compiler worker under Root's original Owner/container; no runtime test."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ci/capability-audit'))
from livecaptions579_arm32_production import worker


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--request-sha256',required=True)
    args=parser.parse_args()
    result=worker({'path':str(args.request),'sha256':args.request_sha256})
    print(json.dumps({'build':result,'scope':'normal production only; new QEMU runtime pending'}))


if __name__=='__main__': main()
