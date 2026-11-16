import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_hw_controller():
    path = REPO_ROOT / "scripts" / "qemu_hw_controller.py"
    spec = importlib.util.spec_from_file_location("qemu_hw_controller_test_mod", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CliAndEnvSupportTest(unittest.TestCase):
    def test_install_sh_accepts_env_vars_and_cli_override(self) -> None:
        install_sh = REPO_ROOT / "scripts" / "install.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mirror = root / "mirror"
            mirror.mkdir()
            pkg_name = "openharmony-qemu-arm64-arm64_virt-2in1"
            pkg_stage = root / pkg_name
            (pkg_stage / "launch").mkdir(parents=True)
            (pkg_stage / "launch" / "macos.command").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
            (pkg_stage / "launch" / "linux.sh").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
            archive = mirror / f"{pkg_name}.tar.gz"
            with tarfile.open(archive, "w:gz") as tf:
                tf.add(pkg_stage, arcname=pkg_name)

            prefix = root / "prefix"
            (prefix / pkg_name).mkdir(parents=True)
            (prefix / pkg_name / "stale.txt").write_text("old", encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "OHOS_QEMU_PREFIX": str(prefix),
                    "OHOS_QEMU_PLATFORM": "macos",
                    "OHOS_QEMU_ARCH": "arm64",
                    "OHOS_QEMU_DEVICE_TYPE": "2in1",
                    "OHOS_QEMU_RELEASE": "v20261114",
                    "OHOS_QEMU_DOWNLOAD_BASE_URL": f"file://{mirror}",
                    "OHOS_QEMU_FORCE": "true",
                    "OHOS_QEMU_KEEP_ARCHIVE": "yes",
                    "OHOS_QEMU_WITHOUT_HAP_SIGNER": "1",
                }
            )
            res = subprocess.run(["bash", str(install_sh)], env=env, capture_output=True, text=True, check=True)
            self.assertIn(f"installed: {prefix / pkg_name}", res.stdout)
            self.assertFalse((prefix / pkg_name / "stale.txt").exists())
            self.assertTrue((prefix / "downloads" / f"{pkg_name}.tar.gz").is_file())

            # CLI --no-force must override OHOS_QEMU_FORCE=true
            fail = subprocess.run(
                ["bash", str(install_sh), "--no-force"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn("already exists", fail.stderr)

    def test_sign_hap_sh_maps_env_vars_and_respects_cli_precedence(self) -> None:
        sign_sh = REPO_ROOT / "scripts" / "sign-hap.sh"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_signer = root / "fake-hap-sign"
            fake_signer.write_text(
                "#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            fake_signer.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "OHOS_HAP_SIGNER": str(fake_signer),
                    "OHOS_HAP_INPUT": "/tmp/unsigned.hap",
                    "OHOS_HAP_OUTPUT": "/tmp/signed.hap",
                    "OHOS_HAP_BUNDLE_NAME": "com.example.env",
                    "OHOS_QEMU_UDID": "UDID_A,UDID_B",
                    "OHOS_HAP_ACLS": "ohos.permission.READ_PASTEBOARD,ohos.permission.INTERNET",
                    "OHOS_HAP_APL": "system_basic",
                    "OHOS_HAP_FORCE": "true",
                }
            )
            res = subprocess.run(["bash", str(sign_sh)], env=env, capture_output=True, text=True, check=True)
            argv = json.loads(res.stdout.strip())
            self.assertEqual(argv[0], "sign")
            self.assertIn("--bundle-name", argv)
            self.assertEqual(argv[argv.index("--bundle-name") + 1], "com.example.env")
            self.assertEqual(argv.count("--device-id"), 2)
            self.assertEqual(argv.count("--acl"), 2)
            self.assertIn("--force", argv)
            self.assertEqual(argv[-1], "/tmp/unsigned.hap")

            # Explicit CLI --bundle-name must override OHOS_HAP_BUNDLE_NAME
            res_cli = subprocess.run(
                ["bash", str(sign_sh), "--bundle-name=com.example.cli", "/tmp/cli.hap"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            argv_cli = json.loads(res_cli.stdout.strip())
            self.assertEqual(argv_cli.count("--bundle-name"), 0)
            self.assertIn("--bundle-name=com.example.cli", argv_cli)
            self.assertNotIn("/tmp/unsigned.hap", argv_cli)
            self.assertIn("/tmp/cli.hap", argv_cli)

    def test_hw_controller_env_defaults_and_locale_commands(self) -> None:
        mod = load_hw_controller()
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="qhw-test-") as td:
            ctrl_sock = str(Path(td) / "ctrl.sock")
            received: list[str] = []

            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(ctrl_sock)
            srv.listen(4)

            def serve_two() -> None:
                for _ in range(2):
                    conn, _ = srv.accept()
                    data = conn.recv(1024).decode("utf-8").strip()
                    received.append(data)
                    conn.sendall(b"OK LOCALE language=en-Latn-US region=US locale=en-Latn-US sa=0\n")
                    conn.close()
                srv.close()

            t = threading.Thread(target=serve_two, daemon=True)
            t.start()

            old_env = os.environ.copy()
            try:
                os.environ["QEMU_HW_CTRL_SOCKET"] = ctrl_sock
                os.environ["QEMU_REGION"] = "GB"
                os.environ["QEMU_HW_COMMAND"] = "locale en"
                rc1 = mod.main([])
                self.assertEqual(rc1, 0)

                # Explicit CLI --region US overrides QEMU_REGION=GB
                rc2 = mod.main(["--region", "US", "locale", "en"])
                self.assertEqual(rc2, 0)
            finally:
                os.environ.clear()
                os.environ.update(old_env)
            t.join(timeout=3.0)
            self.assertEqual(received, ["LOCALE en:GB", "LOCALE en:US"])


if __name__ == "__main__":
    unittest.main()
