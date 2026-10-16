#!/usr/bin/env python3
"""Emit actual broker callback/health bodies for target compilation with real FFRT."""
import argparse
import hashlib
import os
from pathlib import Path
import unittest
from test_batch_network_vpn_broker import VpnBrokerTests
from test_batch_network_vpn_broker_health import BrokerHealthTests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();directory=args.output_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
    outputs={'BATCH_NETWORK_BROKER_CALLBACK_NATIVE_OUTPUT':directory/'vpn-broker-callback-native.cpp',
             'BATCH_NETWORK_BROKER_HEALTH_NATIVE_OUTPUT':directory/'vpn-broker-health-native.cpp'}
    for name,path in outputs.items():os.environ[name]=str(path)
    suite=unittest.TestSuite([VpnBrokerTests('test_actual_new_dispatch_cancels_connected_before_blocking_stop'),
        BrokerHealthTests('test_actual_schedule_epoch_failure_retry_isolation_and_teardown')])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
    for path in outputs.values():print(str(path)+' sha256='+hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
