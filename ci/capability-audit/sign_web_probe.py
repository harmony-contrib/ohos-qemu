#!/usr/bin/env python3
"""Sign a local audit HAP with OpenHarmony's test keys and code-sign block.

Only for QEMU development images. The inputs under --signer-dist are the
public test credentials shipped with developtools/hapsigner, not release keys.
"""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from qemu_test_hap_archive import normalize_archive


FA_PROBE_BUNDLE = 'org.harmonycontrib.qemu.fa.particle'


def fa_probe_config(path: Path) -> bytes:
    """Only the dedicated zero-permission FA caller may omit Stage's block."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate FA configuration key')
            result[key] = value
        return result
    if not path.is_file() or path.is_symlink():
        raise ValueError('regular FA HAP required')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or 'module.json' in names or 'module.json5' in names:
            raise ValueError('FA-only signing must never weaken Stage verification')
        member = archive.getinfo('config.json')
        if member.file_size > 65536:
            raise ValueError('oversized FA configuration')
        content = archive.read(member)
    config = json.loads(content, object_pairs_hook=unique)
    module = config.get('module', {})
    if (config.get('app', {}).get('bundleName') != FA_PROBE_BUNDLE or
            module.get('package') != FA_PROBE_BUNDLE or module.get('reqPermissions', []) != [] or
            module.get('distro', {}).get('moduleType') != 'entry' or
            not isinstance(module.get('abilities'), list) or len(module['abilities']) != 2 or
            module['abilities'][0].get('name') != '.MainAbility' or
            module['abilities'][0].get('type') != 'page' or
            module['abilities'][1].get('name') != '.ParticleService' or
            module['abilities'][1].get('type') != 'service' or
            any(ability.get('permissions', []) != [] for ability in module['abilities'])):
        raise ValueError('only the dedicated ordinary zero-permission FA page/service pair is supported')
    return content


def verify_signed_hap(jar: str, signed: Path, directory: Path, *, fa_no_permissions=False) -> None:
    # The pinned signer accepts .cer, not .pem, for this output. Require the
    # actual verification markers as well as exit status and extracted files.
    if fa_no_permissions:
        fa_probe_config(signed)
    chain, profile = directory / "verified-chain.cer", directory / "verified-profile.p7b"
    completed = subprocess.run([
        "java", "-jar", jar, "verify-app", "-inFile", str(signed),
        "-outCertChain", str(chain), "-outProfile", str(profile),
    ], capture_output=True, text=True)
    log = completed.stdout + completed.stderr
    print(log, end="")
    required = ("verify codesign success", "Digest verify result: true", "verify-app success")
    if not fa_no_permissions:
        required += ("verify permission sign success",)
    if (completed.returncode != 0 or any(marker not in log for marker in required) or
            not chain.is_file() or not chain.stat().st_size or not profile.is_file() or not profile.stat().st_size):
        raise RuntimeError("actual signed HAP code-sign/digest/permission verification did not pass")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signer-dist", type=Path, required=True)
    parser.add_argument("--jar", type=Path, help="Override the OpenHarmony signing tool JAR")
    parser.add_argument("--unsigned", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--udid", required=True)
    parser.add_argument("--sign-code", choices=("0", "1"), default="1")
    parser.add_argument('--fa-no-permissions', action='store_true',
                        help='dedicated zero-permission FA particle caller only; code signing stays mandatory')
    args = parser.parse_args()

    fa_config = None
    if args.fa_no_permissions:
        if args.bundle_name != FA_PROBE_BUNDLE or args.sign_code != '1':
            parser.error('FA probe requires its exact bundle name and code signing')
        fa_config = fa_probe_config(args.unsigned)

    dist = args.signer_dist.resolve()
    profile = json.loads((dist / "UnsgnedDebugProfileTemplate.json").read_text())
    now = int(time.time())
    profile["uuid"] = str(uuid.uuid4())
    profile["validity"] = {"not-before": now - 86400, "not-after": now + 10 * 365 * 86400}
    profile["bundle-info"]["bundle-name"] = args.bundle_name
    profile["bundle-info"]["apl"] = "normal"
    profile["bundle-info"]["app-feature"] = "hos_normal_app"
    profile["debug-info"]["device-ids"] = [args.udid]
    profile["acls"]["allowed-acls"] = []
    profile["permissions"]["restricted-permissions"] = []

    jar = str((args.jar or dist / "hap-sign-tool.jar").resolve())
    keystore = str(dist / "OpenHarmony.p12")
    with tempfile.TemporaryDirectory(prefix="ohos-web-probe-sign-") as temp:
        temp_dir = Path(temp)
        profile_json = temp_dir / "profile.json"
        profile_signed = temp_dir / "profile.p7b"
        normalized_hap = temp_dir / "unsigned-normalized.hap"
        profile_json.write_text(json.dumps(profile, indent=2) + "\n")
        # The local ArkDown ZIP writer emits a ZIP64 CEN extra field rejected
        # by the pinned OpenHarmony signCode parser. Normalize before signing.
        # The host builder can also nest x86_64 libraries under its complete
        # staging path. Repair only that exact known layout before code-sign;
        # preserve every library byte and all permission/application inputs.
        print(json.dumps(normalize_archive(args.unsigned.resolve(), normalized_hap)))
        subprocess.run([
            "java", "-jar", jar, "sign-profile",
            "-keyAlias", "openharmony application profile debug",
            "-signAlg", "SHA256withECDSA", "-mode", "localSign",
            "-profileCertFile", str(dist / "OpenHarmonyProfileDebug.pem"),
            "-inFile", str(profile_json), "-keystoreFile", keystore,
            "-outFile", str(profile_signed), "-keyPwd", "123456",
            "-keystorePwd", "123456",
        ], check=True)
        subprocess.run([
            "java", "-jar", jar, "sign-app",
            "-keyAlias", "openharmony application release",
            "-signAlg", "SHA256withECDSA", "-mode", "localSign",
            "-appCertFile", str(dist / "OpenHarmonyApplication.pem"),
            "-profileFile", str(profile_signed), "-inFile", str(normalized_hap),
            "-keystoreFile", keystore, "-outFile", str(args.output.resolve()),
            "-keyPwd", "123456", "-keystorePwd", "123456", "-signCode", args.sign_code,
        ], check=True)
        if args.fa_no_permissions:
            if fa_probe_config(args.output.resolve()) != fa_config:
                raise RuntimeError('signed FA configuration changed')
            verify_signed_hap(jar, args.output.resolve(), temp_dir, fa_no_permissions=True)
        else:
            verify_signed_hap(jar, args.output.resolve(), temp_dir)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
