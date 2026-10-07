"""Run the actual AST analyzer; fixtures do not prove a guest API works."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
from build_native_arkts11_gap_ledger import compiled_constant_contracts
DEFAULT_TS = "/Applications/DevEco-Studio.app/Contents/plugins/openharmony/ace-server/node_modules/typescript"
SYSCAP = "SystemCapability.Fixture"


def analyze(source, exports):
    typescript = os.environ.get("OHOS_AUDIT_TYPESCRIPT", DEFAULT_TS)
    if not Path(typescript).is_dir() or not shutil.which("node"):
        raise RuntimeError("Node and TypeScript are required; set OHOS_AUDIT_TYPESCRIPT explicitly")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "@ohos.fixture.d.ts").write_text(source)
        runtime = {"profile": "phone", "modules": [{"module": "@ohos.fixture",
            "loaded": True, "audit_status": "loaded", "export_probe_status": 0,
            "exports": exports, "official_profile_syscaps": [SYSCAP]}]}
        (root / "runtime.json").write_text(json.dumps(runtime))
        subprocess.run(["node", str(ROOT / "ci/capability-audit/analyze_arkts_exports.js"),
            "--typescript", typescript, "--api-dir", str(root), "--kits-dir", str(root),
            "--runtime", str(root / "runtime.json"), "--output", str(root / "output.json")],
            check=True, capture_output=True, text=True)
        return json.loads((root / "output.json").read_text())


def tagged(code, since="26 dynamic"):
    return f"\n/** @syscap {SYSCAP}\n * @since {since}\n */\n" + code + "\n"


class ArktsExportClassificationTests(unittest.TestCase):
    def test_const_enum_stays_pending_compiled_caller_not_fake_napi_gap(self):
        source = "declare namespace api {\n" + tagged("const enum Mode { ZERO=0, ONE=1 }")
        source += tagged("enum RealEnum { ZERO=0 }") + tagged("function call(): void;")
        source += "}\nexport default api;"
        report = analyze(source, ["call"])
        row = report["modules"][0]
        self.assertEqual(row["missing_runtime_exports"], ["RealEnum"])
        self.assertEqual(row["compiled_constant_enum_contracts"][0]["name"], "Mode")
        self.assertEqual(row["compiled_constant_enum_contracts"][0]["status"], "compiled_caller_not_verified")
        self.assertEqual(report["summary"]["compiled_constant_enum_contract_count"], 1)

    def test_real_classes_functions_and_static_boundary_are_preserved(self):
        source = "declare namespace api {\n" + tagged("class FactoryValue { value: number; }")
        source += tagged("function missing(): void;") + tagged("enum DynamicEnum { OK=1 }")
        source += tagged("const enum StaticMode { OK=1 }", "26 static") + "}\nexport default api;"
        row = analyze(source, [])["modules"][0]
        self.assertEqual(row["missing_runtime_exports"], ["DynamicEnum", "FactoryValue", "missing"])
        self.assertEqual(row["compiled_constant_enum_contracts"], [])
        self.assertEqual(row["static_only_exports_excluded_from_dynamic_probe"][0]["name"], "StaticMode")

    def test_named_const_enum_and_regular_export_both_retained_in_correct_views(self):
        source = tagged("export const enum Mode { FIRST=1 }") + tagged("export enum Real { FIRST=1 }")
        row = analyze(source, ["Real"])["modules"][0]
        self.assertEqual(row["expected_runtime_exports"], ["Real"])
        self.assertEqual(row["missing_runtime_exports"], [])
        self.assertEqual(row["compiled_constant_enum_contracts"][0]["name"], "Mode")

    def test_ledger_keeps_pending_constants_and_rejects_stale_analyzer_reports(self):
        source = tagged("export const enum Mode { FIRST=1 }")
        report = analyze(source, [])
        pending = compiled_constant_contracts(report)
        self.assertEqual(pending[0]["contracts"][0]["status"], "compiled_caller_not_verified")
        del report["modules"][0]["compiled_constant_enum_contracts"]
        with self.assertRaises(ValueError):
            compiled_constant_contracts(report)


if __name__ == "__main__":
    unittest.main()
