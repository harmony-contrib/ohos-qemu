#!/usr/bin/env python3
"""Compile full SQLite statement source with three actual product commands."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/distributeddatamgr/relational_store/expression_blob_values'
SOURCE = Path('foundation/distributeddatamgr/relational_store/frameworks/native/rdb/src/sqlite_statement.cpp')
TARGET = 'obj/foundation/distributeddatamgr/relational_store/frameworks/native/rdb/src/native_rdb_src/sqlite_statement.o'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    report = run(args, component=COMPONENT, source_file=SOURCE, target=TARGET, caller=__file__,
                 prepare_component_sqlite_headers=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
