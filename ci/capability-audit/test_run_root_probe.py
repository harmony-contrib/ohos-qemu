import argparse
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from run_root_probe import (ARCHES, digest, parse_exit, probe_command, run_probe, validate_archive,
                            validate_boot_archive, validate_elf, validate_identity)
from verify_vibrator_hdi_results import CASES
from verify_native_graphics_results import KINDS as GRAPHICS_KINDS
from test_permission_results import fixture as permission_fixture

RUN = "b" * 32


def package(path, arch="arm64", device="phone", names=("qemu/manifest.json",), value=None):
    data = json.dumps(value if value is not None else {
        "guest_arch": arch, "device_type": device, "device_type_profile": f"qemu_{device}_full_source"
    }).encode()
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))


def elf(path, arch="arm64"):
    header = bytearray(64)
    header[:7] = b"\x7fELF" + bytes((ARCHES[arch][0], 1, 1))
    struct.pack_into("<HH", header, 16, 3, ARCHES[arch][1])
    path.write_bytes(header)


class RootProbeTests(unittest.TestCase):
    def test_live_owned_boot_inventory_reuse_rejects_stale_changed_or_wrong_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'extract/qemu'
            directory.mkdir(parents=True)
            manifest = directory / 'manifest.json'
            manifest.write_text(json.dumps({'guest_arch': 'arm64', 'device_type': 'phone',
                                            'device_type_profile': 'qemu_phone_full_source'}))
            boot_path = root / 'boot.json'
            boot = {'status': 'pass', 'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                    'archive': '/selected/qemu.tar.gz', 'archive_sha256': 'a' * 64,
                    'initial_package_file_sha256': {'manifest.json': digest(manifest)},
                    'test_environment': {'guest_arch': 'arm64', 'device_type': 'phone', 'target': 'own',
                        'boot_id': 'uuid', 'external_keepalive': False, 'qemu_pid': 99999,
                        'qemu_command': 'qemu /tmp/owned.sock', 'qmp_socket': '/tmp/owned.sock',
                        'freshly_extracted_directory': str(directory)}}
            boot_path.write_text(json.dumps(boot))
            self.assertEqual(validate_boot_archive(boot_path, 'a' * 64, 'arm64', 'phone', 'own', 'uuid')[0],
                             json.loads(manifest.read_text()))
            for sha, arch, device, target, uuid in (('b' * 64, 'arm64', 'phone', 'own', 'uuid'),
                    ('a' * 64, 'x86_64', 'phone', 'own', 'uuid'), ('a' * 64, 'arm64', '2in1', 'own', 'uuid'),
                    ('a' * 64, 'arm64', 'phone', 'other', 'uuid'), ('a' * 64, 'arm64', 'phone', 'own', 'stale')):
                with self.assertRaises(ValueError):
                    validate_boot_archive(boot_path, sha, arch, device, target, uuid)
            manifest.write_text(manifest.read_text() + '\n')
            with self.assertRaises(ValueError):
                validate_boot_archive(boot_path, 'a' * 64, 'arm64', 'phone', 'own', 'uuid')

    def test_actual_exit_not_transport_exit_stale_or_ambiguous(self):
        for code in (0, 1, 127, 255):
            self.assertEqual(parse_exit(f"__OHOS_PROBE_EXIT_{RUN}={code}\r\n", RUN), code)
        for output in ("", "0", f"__OHOS_PROBE_EXIT_{'a' * 32}=0\n",
                       f"__OHOS_PROBE_EXIT_{RUN}=256\n", f"__OHOS_PROBE_EXIT_{RUN}=00\n",
                       f"__OHOS_PROBE_EXIT_{RUN}=0\n__OHOS_PROBE_EXIT_{RUN}=1\n"):
            with self.assertRaises(ValueError):
                parse_exit(output, RUN)

    def test_archive_requires_exact_full_profile_arch_and_unambiguous_safe_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "package.tar.gz"
            for arch in ARCHES:
                for device in ("phone", "2in1"):
                    package(path, arch, device)
                    self.assertEqual(validate_archive(path, arch, device)["guest_arch"], arch)
            for names in ((), ("manifest.json",), ("/qemu/manifest.json",), ("../manifest.json",),
                          ("qemu/manifest.json", "other/manifest.json")):
                package(path, names=names)
                with self.assertRaises(ValueError):
                    validate_archive(path, "arm64", "phone")
            for value in ([], {"guest_arch": "aarch64"}, {"device_type": "phone"}):
                package(path, value=value)
                with self.assertRaises(ValueError):
                    validate_archive(path, "arm64", "phone")

    def test_wrong_elf_abi_and_non_root_or_wrong_guest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe"
            for arch in ARCHES:
                elf(path, arch)
                validate_elf(path, arch)
                for other in ARCHES:
                    if arch != other:
                        with self.assertRaises(ValueError):
                            validate_elf(path, other)
                validate_identity("0\r\nphone\r\n" + ARCHES[arch][2] + "\r\n", arch, "phone")
                validate_identity("0\nphone \n" + ARCHES[arch][2] + "\n", arch, "phone")
            for text in ("10001\nphone\naarch64\n", "0\n2in1\naarch64\n", "0\nphone\narmv7l\n",
                         "0\nphone extra\naarch64\n", "0\nphone\naarch64\n\n"):
                with self.assertRaises(ValueError):
                    validate_identity(text, "arm64", "phone")
            path.write_text("not an ELF")
            with self.assertRaises(ValueError):
                validate_elf(path, "arm64")

    def test_commands_clear_injected_library_environment_and_capture_real_exit(self):
        for kind in ("bitmap", "userid", "vibrator-hdi", "permission-registry", "audio-suite", "native-gap-abi",
                     'rs-objects', *GRAPHICS_KINDS):
            text = probe_command(kind, "/data/local/tmp/ohos-audit-" + RUN, RUN)
            self.assertTrue(text.startswith("unset LD_LIBRARY_PATH LD_PRELOAD; "))
            self.assertIn("; probe_status=$?;", text)
            self.assertIn('"$probe_status"', text)
            self.assertNotIn("|| true", text)

    def execute_fixture(self, directory, code=0, wrong_sha=False, transport_failure=False, timeout=False,
                        kind="vibrator-hdi", definitions=None, wrong_names_sha=False, boot_ids=None):
        root = Path(directory)
        binary, archive = root / "probe", root / "package.tar.gz"
        elf(binary)
        package(archive)
        args = argparse.Namespace(kind=kind, probe=binary, archive=archive, arch="arm64",
                                  device="phone", target="127.0.0.1:5681", hdc="hdc", output=root / "result")
        if boot_ids is not None:
            args.boot_id = '12345678-1234-1234-1234-123456789abc'
            boot_values = iter(boot_ids)
        if definitions is not None:
            args.definitions = root / 'definitions.json'
            args.definitions.write_text(json.dumps(definitions))
        remote = "/data/local/tmp/ohos-audit-" + RUN
        rows = [{"kind": "run", "run_id": RUN, "arch": "arm64", "uid": 0, "euid": 0},
                *[{"kind": "case", "name": case, "pass": True} for case in CASES],
                {"kind": "complete", "run_id": RUN}]
        if kind == 'permission-registry':
            _, rows = permission_fixture('phone')
            rows[0]['runId'] = rows[-1]['runId'] = RUN
        calls = []

        def fake(command, **kwargs):
            calls.append(command)
            output = ""
            text = command[-1]
            if "id -u;" in text:
                output = "0\nphone\naarch64\n"
            elif text == 'cat /proc/sys/kernel/random/boot_id':
                output = next(boot_values) + '\n'
            elif text.startswith("umask "):
                output = "__OHOS_PROBE_CREATED_" + RUN + "\n"
            elif text.startswith("chmod "):
                output = ("0" * 64 if wrong_sha else digest(binary)) + "  " + remote + "/probe\n"
            elif text.startswith('sha256sum '):
                path = args.output / 'permission-names.txt'
                output = ('0' * 64 if wrong_names_sha else digest(path)) + '  ' + remote + '/permission-names.txt\n'
            elif text.startswith("unset "):
                if timeout:
                    raise subprocess.TimeoutExpired(command, 90)
                output = f"__OHOS_PROBE_EXIT_{RUN}={code}\n"
            elif text == "cat " + remote + "/stdout.jsonl":
                output = "\n".join(json.dumps(row) for row in rows) + "\n"
            return subprocess.CompletedProcess(command, 1 if transport_failure else 0, output, "")

        with patch("run_root_probe.secrets.token_hex", return_value=RUN):
            result = run_probe(args, fake)
        persisted = json.loads((args.output / "result.json").read_text())
        self.assertEqual(persisted, result)
        return result, calls, args

    def test_fresh_complete_run_preserves_archive_probe_commands_but_does_not_claim_full_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            result, calls, args = self.execute_fixture(directory)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["archive_sha256"], digest(args.archive))
            self.assertEqual(result["probe_sha256"], digest(args.probe))
            self.assertEqual(result["probe_exit_code"], 0)
            self.assertEqual(len(result["commands"]), len(calls))
            self.assertFalse(result["first_artifact_behavior_gate_passed"])
            self.assertEqual(result["archive_binding"], "caller_selected_archive_not_automatically_boot_attested")
            self.assertEqual(sum("send" in call for call in calls), 1)
            with self.assertRaises(FileExistsError):
                run_probe(args)

    def test_nonzero_guest_exit_is_failure_even_when_hdc_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _, args = self.execute_fixture(directory, code=1)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["probe_exit_code"], 1)
            self.assertTrue((args.output / "stdout.jsonl").is_file())

    def test_enclosing_boot_identity_checked_before_and_after_actual_probe(self):
        expected = '12345678-1234-1234-1234-123456789abc'
        with tempfile.TemporaryDirectory() as directory:
            result, _, _ = self.execute_fixture(directory, boot_ids=[expected, expected])
            self.assertEqual(result['status'], 'pass')
            self.assertEqual(result['boot_id'], expected)
            self.assertTrue(result['kernel_boot_id_unchanged'])
        for values in (['stale'], ['aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'],
                       [expected, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa']):
            with tempfile.TemporaryDirectory() as directory:
                result, _, _ = self.execute_fixture(directory, boot_ids=values)
                self.assertEqual(result['status'], 'fail')
                self.assertTrue(result['failures'])

    def test_changed_executable_transport_failure_and_timeout_are_fail_closed(self):
        for option in ("wrong_sha", "transport_failure", "timeout"):
            with tempfile.TemporaryDirectory() as directory:
                result, calls, _ = self.execute_fixture(directory, **{option: True})
                self.assertEqual(result["status"], "fail")
                self.assertTrue(result["failures"])
                self.assertNotIn("result", result)
                # A timed-out privileged probe is never automatically replayed.
                self.assertLessEqual(sum(call[-1].startswith("unset ") for call in calls), 1)

    def test_permission_input_is_bound_to_source_and_transferred_without_system_libraries(self):
        source, _ = permission_fixture('phone')
        with tempfile.TemporaryDirectory() as directory:
            result, calls, args = self.execute_fixture(directory, kind='permission-registry', definitions=source)
            self.assertEqual(result['status'], 'pass')
            self.assertEqual(result['source_permission_count'], 2)
            self.assertEqual(result['definitions_sha256'], digest(args.definitions))
            self.assertEqual(result['names_sha256'], digest(args.output / 'permission-names.txt'))
            self.assertEqual((args.output / 'permission-names.txt').read_text(),
                             'ohos.permission.GENERAL\nohos.permission.PC_ONLY\n')
            sent = [call for call in calls if 'send' in call]
            self.assertEqual(len(sent), 2)
            self.assertTrue(all(call[-1].startswith(result['guest_directory'] + '/') for call in sent))
            self.assertEqual(result['result']['boundary_count'], 4)
        with tempfile.TemporaryDirectory() as directory:
            result, calls, _ = self.execute_fixture(directory, kind='permission-registry', definitions=source,
                                                    wrong_names_sha=True)
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(any(call[-1].startswith('unset ') for call in calls))

    def test_invalid_or_misapplied_permission_definitions_fail_before_guest_commands(self):
        source, _ = permission_fixture('phone')
        duplicate = copy.deepcopy(source)
        duplicate['definePermissions'].append(duplicate['definePermissions'][0])
        for value, kind in ((None, 'permission-registry'), ({'definePermissions': []}, 'permission-registry'),
                            (duplicate, 'permission-registry'), (source, 'vibrator-hdi')):
            with tempfile.TemporaryDirectory() as directory:
                result, calls, _ = self.execute_fixture(directory, kind=kind, definitions=value)
                self.assertEqual(result['status'], 'fail')
                self.assertEqual(calls, [])
        for name in ('invalid!', 'ohos.permission.; echo unsafe', '', 'ohos.permission.' + 'A' * 241):
            bad = copy.deepcopy(source)
            bad['definePermissions'][0]['name'] = name
            with tempfile.TemporaryDirectory() as directory:
                result, calls, _ = self.execute_fixture(directory, kind='permission-registry', definitions=bad)
                self.assertEqual(result['status'], 'fail')
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
