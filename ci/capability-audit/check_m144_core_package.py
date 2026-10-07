#!/usr/bin/env python3
"""Validate fixed real packaging inputs and profile signing in owned staging.

This does not build an engine, sign a HAP, install a guest, or pass its behavior
gate. Production M144 sources must be read-only to this process.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

FILES = (
    "src/third_party/ohos_nweb_hap/build-profile.json5",
    "src/third_party/ohos_nweb_hap/dependencies/rk/signature/UnsgnedReleasedProfileTemplate.json",
    "src/arkweb/build/hap/build_hap_rk.py",
    "src/arkweb/build/sign.sh",
    "src/arkweb/build/hap/hap.gni",
    'src/third_party/ohos_nweb_hap/hvigorw',
    'src/third_party/ohos_nweb_hap/hvigor/hvigor-config.json5',
    'src/third_party/ohos_nweb_hap/oh-package.json5',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_profile_content(document):
    if document.get("verifiedPassed") is not True:
        raise ValueError("release profile signature was not verified")
    content = document.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        raise ValueError("verified profile content is missing")
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="M144 parent containing src")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, repo, output = args.source_root.resolve(), args.repo_root.resolve(), args.output.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError("fixed M144 production source must be read-only")
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("validation output must be separate from fixed sources")
    output.mkdir(parents=True, exist_ok=False)
    result = {"scope": "actual_pinned_packaging_inputs_and_release_profile_signature_NOT_engine_HAP_or_guest_acceptance",
              "status": "fail", "first_artifact_behavior_gate_passed": False,
              "source_mounted_readonly": True, "commands": [], "original_sha256": {}, "failures": []}

    def run(argv, name):
        log = output / (name + ".log")
        with log.open("x") as stream:
            process = subprocess.run([str(value) for value in argv], stdout=stream, stderr=subprocess.STDOUT,
                                     cwd=output, check=False)
        result["commands"].append({"argv": [str(value) for value in argv], "exit_code": process.returncode,
                                   "log": str(log), "sha256": sha(log)})
        if process.returncode:
            raise ValueError(name + " failed; preserve the diagnostic log")
        return log.read_text(errors="replace")

    try:
        for relative, expected in (("src", "a8168622b056f25c2e68d5f12fe2759bad2d9a44"),
                                   ("src/arkweb", "f3d904432cc1c57468f2b7fe01979d25e0157581")):
            actual = subprocess.run(["git", "-C", str(source / relative), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True).stdout.strip()
            if actual != expected:
                raise ValueError("pinned packaging source differs: " + relative)
        for relative in FILES:
            original, target = source / relative, output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            result["original_sha256"][relative] = sha(original)
        frozen = output / "frozen-inputs"
        component = "patches/common/web/arkweb/m144_core_package"
        shutil.copytree(repo / component, frozen / component)
        shutil.copytree(repo / "patches/lib", frozen / "patches/lib")
        result["patch_input_sha256"] = {str(path.relative_to(frozen)): sha(path)
                                         for path in (frozen / component).rglob("*") if path.is_file()}
        for iteration in range(2):
            run(["bash", frozen / component / "apply.sh", "--source-root", output], f"apply-{iteration}")
        result["patched_sha256"] = {relative: sha(output / relative) for relative in FILES}
        build_profile = FILES[0]
        if (output / build_profile).read_bytes() != (source / build_profile).read_bytes().replace(
                b'"compileSdkVersion": 24', b'"compileSdkVersion": "26.0.0"').replace(
                b'"compileSdkVersion": 26,', b'"compileSdkVersion": "26.0.0",'):
            raise ValueError("HAP SDK repair changed other project fields")
        profile = FILES[1]
        before, after = (json.loads((root / profile).read_text()) for root in (source, output))
        before["validity"]["not-after"] = 2208988800
        if before != after or after["bundle-info"] != {
                **before["bundle-info"], "bundle-name": "com.ohos.arkwebcore",
                "apl": "normal", "app-feature": "hos_normal_app"}:
            raise ValueError("release profile identity/permissions changed")
        run(["bash", "-n", output / FILES[3]], "signer-shell-syntax")
        sdk = source / "src/ohos_sdk/26/toolchains/lib"
        inputs = (sdk / "hap-sign-tool.jar", sdk / "OpenHarmonyProfileRelease.pem", sdk / "OpenHarmony.p12")
        result["signing_input_sha256"] = {str(path): sha(path) for path in inputs}
        signed_profile = output / "public-core.p7b"
        run(["java", "-jar", inputs[0], "sign-profile", "-keyAlias", "openharmony application profile release",
             "-signAlg", "SHA256withECDSA", "-mode", "localSign", "-profileCertFile", inputs[1],
             "-inFile", output / profile, "-keystoreFile", inputs[2], "-outFile", signed_profile,
             "-keyPwd", "123456", "-keystorePwd", "123456"], "sign-profile")
        extracted = output / "verified-public-core.json"
        verified = run(["java", "-jar", inputs[0], "verify-profile", "-inFile", signed_profile,
                        "-outFile", extracted], "verify-profile")
        if "verify-profile success" not in verified or verified_profile_content(json.loads(extracted.read_text())) != after:
            raise ValueError("profile verification did not attest the exact candidate profile")
        if any(sha(source / name) != digest for name, digest in result["original_sha256"].items()):
            raise ValueError("production input changed during package-input validation")
        if any(sha(Path(name)) != digest for name, digest in result["signing_input_sha256"].items()):
            raise ValueError("release signing input changed during validation")
        result["signed_profile_sha256"] = sha(signed_profile)
        result["verified_profile"] = {"bundle_name": after["bundle-info"]["bundle-name"],
                                      "apl": after["bundle-info"]["apl"],
                                      "app_feature": after["bundle-info"]["app-feature"],
                                      "valid_until": after["validity"]["not-after"],
                                      "permissions_and_certificate_unchanged": True}
        result["status"] = "pass"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["failures"].append(str(error))
    (output / "package-input-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "failures": result["failures"], "scope": result["scope"]}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
