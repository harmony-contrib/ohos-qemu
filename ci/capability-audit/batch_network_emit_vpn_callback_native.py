#!/usr/bin/env python3
"""Emit actual callback bodies for an OHOS native real-FFRT regression probe."""
import argparse
import hashlib
import os
from pathlib import Path
import unittest
from test_batch_network_vpn_callbacks import VpnCallbackTests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target=args.output.resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    os.environ['BATCH_NETWORK_CALLBACK_NATIVE_OUTPUT']=str(target)
    suite=unittest.TestSuite([VpnCallbackTests('test_actual_functions_reentry_epoch_owner_order_teardown_and_delivery_failures')])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
    print(str(target))
    print('sha256='+hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
