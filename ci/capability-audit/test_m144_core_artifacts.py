"""Synthetic contract fixtures only; none is an actual source HAP or guest pass."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import m144_core_artifacts as core
import verify_m144_hap_native_transform as transform
from snapshot_build_inputs import snapshot
import test_arkweb_core_image as hap_fixtures
from test_access_token_kernel import write_preimages

COMPONENT = ROOT / "patches/common/base/web/webview/core_hap_source"
spec = importlib.util.spec_from_file_location("source_core_install", COMPONENT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class CoreArtifactTests(unittest.TestCase):
    def setUp(self):
        # Portable fixture tools are deliberately synthetic, not fixed-release
        # binaries or actual transformation evidence. The real tool replay is
        # independently required by the Docker production pipeline.
        self.fixture_tools = {name: ('synthetic unit tool: ' + name).encode()
                              for name in transform.OFFICIAL_INPUTS}
        fixture_hashes = {name: __import__('hashlib').sha256(value).hexdigest()
                          for name, value in self.fixture_tools.items()}
        for module in (core, transform):
            mocking = patch.object(module, 'OFFICIAL_INPUTS', fixture_hashes)
            mocking.start()
            self.addCleanup(mocking.stop)

    def fixture(self, root, arch="arm64"):
        root.mkdir(parents=True)
        frozen = root / "frozen-build-inputs"
        frozen.mkdir()
        manifest = snapshot(ROOT, frozen)
        lock = core.load_lock(ROOT / "scripts/m144_release_source_lock.json")
        pins = {p["path"]: p["revision"] for p in lock["projects"]}
        write(root / "release-source-pins.json", {
            "source_lock_sha256": core.checksum(ROOT / "scripts/m144_release_source_lock.json"),
            "source_pins": pins, "release_lfs_objects": [{"path": "build/pgo/ohos/arkweb.profdata",
                "sha256": "c98db0441494ecd018d7decbd2aa9b37ec61fd3e960b56e7e81eb19e0afceb1b", "size": 262100672}]})
        write(root / "sdk-preparation-evidence.json", {"sdk_metadata": {"apiVersion": "26", "version": "26.0.0.39"}})
        write(root / 'sdk-bti-runtime-evidence.json', {'status': 'pass', 'source_revision': core.SDK_LLVM_REVISION,
            'builder_sha256': core.checksum(ROOT / 'scripts/build_m144_sdk_bti_runtimes.py'),
            'archives': {name: {'all_objects_BTI': True, 'defined_C_symbols_match_original': True}
                         for name in core.ARCHIVES}})
        write(root / 'release-tools-evidence.json', {'status': 'pass', 'chromium_revision': core.CHROMIUM,
            'gn': {'revision': core.GN_REVISION}, 'tools': [
                {'source': {'sha256sum': value}, 'archive_sha256': value, 'installed': {'file_count': 1}}
                for value in sorted(core.TOOL_PAYLOADS)]})
        tools = core.hap_tool_recipe(ROOT)
        for name in ('hap-host-tools-native.json', 'hap-host-tools-package.json'):
            write(root / name, {'status': 'pass', 'lock': tools['lock'],
                'recipe_sha256': tools['recipe_sha256'], 'installed_tree_sha256': 'a' * 64,
                'sdk_metadata_modified': False, 'dependency_network_required': False,
                'official_tool_code_modified': False,
                'sdk_version_boundary': {'status': 'pass', 'rows': [
                    {'value': value, 'expected': wanted, 'accepted': wanted} for value, wanted in core.VERSION_CASES]},
                'preflight': {'exit_code': 0, 'stdout': tools['lock']['hvigor_version'] + '\n'},
                'release_node': {key: tools['lock'][key] for key in ('build_revision', 'node_version', 'npm_version')}})
        write(root / "native-build-inputs.json", {"arch": arch,
            "sdk_evidence_sha256": core.checksum(root / "sdk-preparation-evidence.json"),
            "sdk_bti_runtime_evidence_sha256": core.checksum(root / "sdk-bti-runtime-evidence.json"),
            "release_tools_evidence_sha256": core.checksum(root / "release-tools-evidence.json"),
            "hap_host_tools_evidence_sha256": core.checksum(root / 'hap-host-tools-native.json'),
            "release_source_graph_sha256": core.checksum(root / "release-source-pins.json"),
            "frozen_manifest_sha256": core.checksum(frozen / "build-inputs.json"),
            "frozen_tree_sha256": manifest["tree_sha256"]})
        hap_fixtures.ArkWebCoreImageTests().hap(root / "ArkWebCore.hap", core.ARCHES[arch])
        observed = core.verify_hap(root / "ArkWebCore.hap", core.ARCHES[arch])
        native_libraries = {Path(name).name: value for name, value in observed["native_libraries"].items()}
        write(root / "native-build-evidence.json", {"exit_code": 0, "failures": [], "artifacts": native_libraries,
            "native_inputs_sha256": core.checksum(root / "native-build-inputs.json")})
        prefix = "patches/common/web/arkweb/m144_core_package/"
        files = {name: digest for name, digest in manifest["files_sha256"].items() if name.startswith(prefix)}
        for name in files:
            target = root / "hap-build-inputs" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        write(root / "package-build-inputs.json", {"native_evidence_sha256": core.checksum(root / "native-build-evidence.json"),
            'hap_host_tools_evidence_sha256': core.checksum(root / 'hap-host-tools-package.json'),
            "frozen_inputs_sha256": files})
        write(root / "package-build-evidence.json", {"exit_code": 0, "hap_sha256": observed["hap_sha256"]})
        write(root / "source-hap-abi-evidence.json", {"status": "pass", **observed})
        (root / "verify-app.log").write_text("synthetic unit fixture: verify-app success")
        for name in ("verified-app-cert.cer", "verified-app-profile.p7b"):
            (root / name).write_bytes(b"synthetic signature fixture, not a signed HAP")
        write(root / "kernel-permission-input.json", {"scope": "unchanged_official_HAP_kernelpermission_input",
              "source_revision": pins["src"], 'files_sha256': {
                  'third_party/ohos_nweb_hap/' + name: digest for name, digest in core.OFFICIAL_INPUTS.items()}})
        import zipfile
        with zipfile.ZipFile(root / 'ArkWebCore.hap') as archive:
            for name in core.REQUIRED_LIBRARIES:
                content = archive.read('libs/' + observed['abi'] + '/' + name)
                for directory in ('native-libraries', 'hap-transform-work/stripped'):
                    target = root / directory / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
        for name, content in self.fixture_tools.items():
            target = root / 'hap-transform-work/tools' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        write(root / 'hap-native-transform.json', {'schema_version': 1, 'scope': transform.SCOPE,
            'status': 'pass', 'failures': [], 'first_artifact_behavior_gate_passed': False,
            'verifier_sha256': core.checksum(ROOT / 'scripts/verify_m144_hap_native_transform.py'),
            'sdk_strip_sha256': transform.SDK_STRIP_SHA256, 'official_inputs_sha256': core.OFFICIAL_INPUTS,
            'native_evidence_sha256': core.checksum(root / 'native-build-evidence.json'),
            'signed_hap_sha256': observed['hap_sha256'], 'kernelpermission_command': {'exit_code': 0},
            'libraries': {name: {'native': {'sha256': value['sha256'], 'size': value['size']},
                'stripped': {'sha256': value['sha256'], 'size': value['size']}, 'strip_exit_code': 0,
                'kernelpermission_applied': name == 'libarkweb_engine.so'}
                for name, value in native_libraries.items()}})
        return root

    def test_hap_transform_rejects_changed_original_final_tools_and_failed_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(Path(directory) / 'arm64')
            native = core.document(root / 'native-build-evidence.json')
            observed = core.verify_hap(root / 'ArkWebCore.hap', 'arm64')
            for relative in ('native-libraries/libffmpeg.so',
                             'hap-transform-work/stripped/libarkweb_render.so',
                             'hap-transform-work/tools/encaps.json'):
                target = root / relative
                original = target.read_bytes()
                target.write_bytes(original + b'unknown change')
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    transform.validate(root, native, observed, ROOT)
                target.write_bytes(original)
            target = root / 'hap-native-transform.json'
            original = target.read_bytes()
            changes = [lambda d: d.update(status='fail'), lambda d: d.update(failures=['failure']),
                lambda d: d['libraries']['libffmpeg.so'].update(strip_exit_code=False),
                lambda d: d['libraries']['libffmpeg.so'].update(kernelpermission_applied=True),
                lambda d: d['libraries'].pop('libarkweb_engine.so'),
                lambda d: d['kernelpermission_command'].update(exit_code=1)]
            for change in changes:
                value = __import__('json').loads(original)
                change(value)
                write(target, value)
                with self.assertRaises(ValueError):
                    transform.validate(root, native, observed, ROOT)
            target.write_bytes(original)
            transform.validate(root, native, observed, ROOT)

    def test_record_verify_and_tampered_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(Path(directory) / "arm64")
            record = core.record(root, "arm64", ROOT)
            self.assertFalse(record["first_artifact_behavior_gate_passed"])
            self.assertFalse(core.validate(root, "arm64", ROOT)["arkweb_behavior_validated"])
            with self.assertRaises(ValueError):
                core.record(root, "arm64", ROOT)
            (root / "verify-app.log").write_text("tampered")
            with self.assertRaises(ValueError):
                core.validate(root, "arm64", ROOT)

    def test_failed_native_incomplete_graph_wrong_sdk_and_wrong_abi_rejected(self):
        changes = (("native-build-evidence.json", lambda d: d.update(exit_code=1)),
                   ("sdk-bti-runtime-evidence.json", lambda d: d.update(status='fail')),
                   ("release-tools-evidence.json", lambda d: d['tools'].pop()),
                   ('hap-host-tools-native.json', lambda d: d.update(status='fail')),
                   ('hap-host-tools-package.json', lambda d: d.update(installed_tree_sha256='b' * 64)),
                   ("release-source-pins.json", lambda d: d["source_pins"].popitem()),
                   ("sdk-preparation-evidence.json", lambda d: d["sdk_metadata"].update(apiVersion="24")),
                   ("release-source-pins.json", lambda d: d.update(release_lfs_objects=[])))
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(Path(directory) / "arm64")
            for name, change in changes:
                original = (root / name).read_bytes()
                data = json.loads(original)
                change(data)
                write(root / name, data)
                with self.assertRaises(ValueError):
                    core.check_build(root, "arm64", ROOT)
                (root / name).write_bytes(original)
            with self.assertRaises(ValueError):
                core.check_build(root, "x86_64", ROOT)

    def test_stale_frozen_native_patch_and_missing_signature_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(Path(directory) / "arm64")
            path = root / "frozen-build-inputs/patches/common/web/arkweb/m144_private_contract/apply.sh"
            original = path.read_bytes()
            path.write_bytes(original + b"\n# changed\n")
            with self.assertRaises(ValueError):
                core.check_build(root, "arm64", ROOT)
            path.write_bytes(original)
            (root / "verify-app.log").write_text("signature failure")
            with self.assertRaises(ValueError):
                core.check_build(root, "arm64", ROOT)

    def test_unsafe_duplicate_and_aliased_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "document.json"
            path.write_text('{"status":"pass","status":"fail"}')
            with self.assertRaises(ValueError):
                core.document(path)
            for name in ("../other", "/tmp/other", "a\\other"):
                with self.assertRaises(ValueError):
                    core.checked_file(root, name)
            (root / "alias").symlink_to(path)
            with self.assertRaises(ValueError):
                core.checked_file(root, "alias")

    def test_installer_keeps_official_prebuilts_and_rejects_unknown_core(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, artifacts = root / "source", root / "artifacts"
            source.mkdir()
            write_preimages(source, tuple(COMPONENT.glob("*.patch")))
            prebuilt = source / "base/web/webview/ohos_nweb/prebuilts/arm64/ArkWebCore.hap"
            prebuilt.parent.mkdir(parents=True)
            prebuilt.write_bytes(b"official preserved")
            incoming = artifacts / "arm64/ArkWebCore.hap"
            incoming.parent.mkdir(parents=True)
            incoming.write_bytes(b"synthetic source fixture")
            record = {"hap_sha256": core.checksum(incoming), "core_artifact_sha256": "1" * 64,
                      "release_source_lock_sha256": "2" * 64}
            with patch.object(installer, "validate", return_value=record), \
                    patch.object(installer.subprocess, "check_output", return_value=installer.WEBVIEW_REVISION):
                for _ in range(2):
                    installer.install(source, artifacts, ["arm64_virt"])
                self.assertEqual(prebuilt.read_bytes(), b"official preserved")
                target = source / "base/web/webview/ohos_nweb/qemu-core/arm64/ArkWebCore.hap"
                target.write_bytes(b"user modified")
                with self.assertRaises(ValueError):
                    installer.install(source, artifacts, ["arm64_virt"])
                self.assertEqual(target.read_bytes(), b"user modified")
                text = (source / "base/web/webview/ohos_nweb/BUILD.gn").read_text()
                self.assertIn('web_source = "qemu-core/x86_64/ArkWebCore.hap"', text)

    def test_source_installed_before_profile_and_packaged_hap_bound_to_source(self):
        build = (ROOT / "scripts/build_standard_qemu_in_docker.sh").read_text()
        self.assertLess(build.index('core_hap_source/apply.sh'), build.index('  configure_qemu_device_profile\n'))
        package = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        self.assertIn('--source-artifact-root "${QEMU_ARKWEB_CORE_ARTIFACTS:', package)
        self.assertIn('arkweb-source-core.json', package)


if __name__ == "__main__":
    unittest.main()
