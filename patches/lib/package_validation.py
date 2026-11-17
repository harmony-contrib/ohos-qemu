"""Keep static packaging checks distinct from new-archive behavior evidence."""
import argparse
import json
from pathlib import Path


PACKAGING_SCOPE = {
    "capability_flags_scope": "static_packaging_contract_only",
    "new_package_boot_tested": False,
    "runtime_behavior_tested": False,
    "first_artifact_behavior_gate_passed": False,
    "runtime_evidence_location": "external_report_bound_to_archive_sha256",
}


def validate_packaging_scope(manifest):
    scope = manifest.get("validation")
    if not isinstance(scope, dict) or set(scope) != set(PACKAGING_SCOPE) or any(
        type(scope[key]) is not type(value) or scope[key] != value
        for key, value in PACKAGING_SCOPE.items()
    ):
        raise ValueError("package must identify static checks without claiming new-archive runtime validation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    validate_packaging_scope(json.loads(args.manifest.read_text()))
    print("PASS: static packaging scope (not boot/behavior or first-artifact gate)")


if __name__ == "__main__":
    main()
