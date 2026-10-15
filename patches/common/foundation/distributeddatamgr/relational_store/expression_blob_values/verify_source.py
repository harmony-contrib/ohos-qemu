"""Exact Release SQLite expression/empty BLOB value repair; not guest proof."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/distributeddatamgr/relational_store'
REVISION = '41f08a8ee0140ebc525f9f9152906a312c6cf30e'
FILES = (('frameworks/native/rdb/src/sqlite_statement.cpp', '530c001223a99dcb09ccad27db8502f60861a1f965fc762fecc77a5cdd3bf1f8', 'db0d35950401945b0fa074296561fef7258e7eacce296843f71b028b9a16125e'),)

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
