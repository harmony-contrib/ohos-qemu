#!/usr/bin/env python3
"""Run one probe in an isolated QA guest; this is not the full first-package gate.

Transfer only the executable, never replacement system libraries. Record the
guest process exit separately from HDC's transport exit. The selected archive
must be the archive used to boot the guest. Optional --boot-evidence binds it
to the enclosing live owned VM and its initial full archive inventory; without
that option the caller attests the relationship. Neither mode claims ordinary
app/permission/UI coverage or the complete new-package gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import struct
import subprocess
import tarfile
import time

from verify_access_token_results import verify as verify_bitmap
from verify_userid_results import verify as verify_userid
from verify_vibrator_hdi_results import verify as verify_vibrator
from verify_native_graphics_results import KINDS as GRAPHICS_KINDS, verify as verify_graphics
from verify_permission_results import verify as verify_permissions
from verify_audio_suite_results import verify as verify_audio_suite
from verify_bpf_results import verify as verify_bpf
from verify_binder_sender_results import verify as verify_binder_sender
from verify_rs_object_results import verify as verify_rs_objects
from verify_screen_modes import verify as verify_screen_modes
from verify_project_quota import data_device, verify as verify_project_quota
from verify_native_gap_abi_results import validate_definitions as validate_native_abi, verify as verify_native_abi

ARCHES = {"arm64": (2, 183, "aarch64"), "armv7a": (1, 40, "armv7l"),
          "x86_64": (2, 62, "x86_64")}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def validate_elf(path, arch):
    with path.open("rb") as stream:
        header = stream.read(64)
    elf_class, machine, _ = ARCHES[arch]
    if (len(header) < 52 or header[:4] != b"\x7fELF" or header[4:7] != bytes((elf_class, 1, 1)) or
            struct.unpack_from("<H", header, 16)[0] not in (2, 3) or
            struct.unpack_from("<H", header, 18)[0] != machine):
        raise ValueError("probe is not an executable ELF for the selected architecture")


def validate_archive(path, arch, device):
    manifests = []
    with tarfile.open(path, "r|gz") as archive:
        for item in archive:
            name = PurePosixPath(item.name)
            if name.name != "manifest.json":
                continue
            if (not item.isfile() or name.is_absolute() or ".." in name.parts or
                    len(name.parts) != 2 or item.size > 1024 * 1024):
                raise ValueError("invalid package manifest entry")
            manifests.append(json.load(archive.extractfile(item)))
    if len(manifests) != 1:
        raise ValueError("exactly one top-level package manifest is required")
    return validate_manifest(manifests[0], arch, device)


def validate_manifest(manifest, arch, device):
    profile = f"qemu_{device}_full_source"
    if (not isinstance(manifest, dict) or manifest.get("guest_arch") != arch or
            manifest.get("device_type") != device or manifest.get("device_type_profile") != profile):
        raise ValueError("selected package architecture/device/profile mismatch")
    return manifest


def validate_boot_archive(boot_path, archive_sha, arch, device, target, boot_id):
    """Reuse the owned boot's already checked archive inventory, not a cache.

    The boot loader checked every member and duplicate, extracted the archive,
    and verified all actual package checksums. Avoid decompressing multi-GiB
    userdata again for every tiny probe. Actual host process and kernel ID are
    separately checked by the caller; this never attests the full gate.
    """
    if boot_path.is_symlink() or not boot_path.is_file():
        raise ValueError('regular owned boot evidence required')
    boot_path = boot_path.resolve()
    boot = json.loads(boot_path.read_text())
    env = boot.get('test_environment', {})
    if (boot.get('status') != 'pass' or boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate'
            or boot.get('archive_sha256') != archive_sha or env.get('guest_arch') != arch
            or env.get('device_type') != device or env.get('target') != target
            or not boot_id or env.get('boot_id') != boot_id or env.get('external_keepalive') is not False
            or type(env.get('qemu_pid')) is not int or env['qemu_pid'] <= 1 or
            not env.get('qemu_command') or not env.get('qmp_socket')):
        raise ValueError('probe must match the original owned archive, VM and kernel boot')
    directory = Path(env['freshly_extracted_directory'])
    expected = boot_path.parent / 'extract' / Path(boot['archive']).name.removesuffix('.tar.gz')
    manifest = directory / 'manifest.json'
    if (directory.resolve() != expected.resolve() or directory.is_symlink() or manifest.is_symlink() or
            not manifest.is_file() or digest(manifest) != boot.get('initial_package_file_sha256', {}).get('manifest.json')):
        raise ValueError('actual owned extraction manifest changed or was substituted')
    return validate_manifest(json.loads(manifest.read_text()), arch, device), boot


def validate_identity(output, arch, device):
    # The pinned param CLI appends a space to successful values. Preserve the
    # strict three-record contract while accepting that formatting, not an
    # additional token, extra output or a different device identity.
    records = [line.strip() for line in output.replace("\r", "").splitlines()]
    if records != ["0", device, ARCHES[arch][2]]:
        raise ValueError("target is not root in the requested architecture/device QA guest")


def parse_exit(output, run_id):
    match = re.fullmatch(r"__OHOS_PROBE_EXIT_" + re.escape(run_id) + r"=(0|[1-9][0-9]{0,2})\n?",
                         output.replace("\r", ""))
    if not match or int(match[1]) > 255:
        raise ValueError("missing, mixed or stale actual guest process exit record")
    return int(match[1])


def probe_command(kind, remote, run_id, quota_device=None):
    if kind == 'project-quota':
        if not isinstance(quota_device, str) or not re.fullmatch(r'/dev/block/vd[a-z]+[0-9]*', quota_device):
            raise ValueError('project quota requires the validated actual userdata device')
        arguments = ['--disposable-guest', quota_device, run_id]
    else:
        arguments = ([] if kind in GRAPHICS_KINDS or kind in ("audio-suite", "screen-modes") else
                 {"bitmap": ["--privileged", run_id], "userid": ["--privileged", run_id, "0"],
                  "vibrator-hdi": [run_id],
                  "bpf": [run_id],
                  "binder-sender": [run_id],
                  "rs-objects": [run_id],
                  "native-gap-abi": [run_id],
                  "permission-registry": [remote + "/permission-names.txt", run_id]}[kind])
    executable = shlex.join([remote + "/probe", *arguments])
    return ("unset LD_LIBRARY_PATH LD_PRELOAD; " + executable +
            " >" + shlex.quote(remote + "/stdout.jsonl") +
            " 2>" + shlex.quote(remote + "/stderr.txt") + "; probe_status=$?; " +
            "printf '__OHOS_PROBE_EXIT_" + run_id + "=%s\\n' \"$probe_status\"")


def verify_result(kind, log, arch, run_id, code, definitions=None, device=None):
    if kind == 'project-quota':
        if type(code) is not int or code != 0:
            raise ValueError('actual kernel quota process failed')
        return verify_project_quota(log, run_id)
    if kind == 'screen-modes':
        if type(code) is not int or code != 0:
            raise ValueError('actual display readback process failed')
        return verify_screen_modes(log)
    if kind in GRAPHICS_KINDS:
        return verify_graphics(kind, log, code)
    if kind == "vibrator-hdi":
        return verify_vibrator(log, arch, run_id, code)
    if kind == "permission-registry":
        return verify_permissions(definitions, log, device, run_id, code)
    if kind == "audio-suite":
        return verify_audio_suite(log, code)
    if kind == "bpf":
        return verify_bpf(log, arch, run_id, code)
    if kind == "binder-sender":
        return verify_binder_sender(log, arch, run_id, code)
    if kind == "rs-objects":
        return verify_rs_objects(log, arch, run_id, code)
    if kind == "native-gap-abi":
        return verify_native_abi(log, definitions, arch, device, run_id, code)
    rows = [json.loads(line) for line in log.splitlines() if line.strip()]
    if kind == "bitmap":
        return verify_bitmap(rows, arch, "privileged", run_id, code)
    return verify_userid(rows, arch, "privileged", run_id, code)


def run_probe(args, runner=subprocess.run):
    # A fresh directory is mandatory. Never append to, or reuse, previous logs.
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = secrets.token_hex(16)
    remote = "/data/local/tmp/ohos-audit-" + run_id
    evidence = {"schema_version": 1, "status": "fail", "kind": args.kind, "run_id": run_id,
                "target": args.target, "arch": args.arch, "device": args.device,
                "hdc_server_port": os.environ.get("OHOS_HDC_SERVER_PORT", "8710"),
                "scope": "isolated_root_probe_only_not_normal_app_or_full_capability_gate",
                "archive_binding": "caller_selected_archive_not_automatically_boot_attested",
                "first_artifact_behavior_gate_passed": False, "guest_directory": remote,
                "commands": [], "failures": []}

    def command(arguments, timeout=60):
        started = time.monotonic()
        record = {"argv": [str(arg) for arg in arguments], "timeout_seconds": timeout}
        evidence["commands"].append(record)
        try:
            result = runner(record["argv"], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            record.update(timed_out=True, elapsed_seconds=time.monotonic() - started)
            raise ValueError("HDC command timed out; guest process may still be running; do not auto-replay")
        record.update(transport_exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr,
                      elapsed_seconds=time.monotonic() - started)
        if result.returncode != 0:
            raise ValueError("HDC transport command failed, not a successful probe exit")
        return result.stdout

    def shell(script, timeout=60):
        return command([args.hdc, "-t", args.target, "shell", script], timeout)

    try:
        if args.kind == 'project-quota' and not getattr(args, 'boot_evidence', None):
            raise ValueError('quota tests require an enclosing live owned disposable package boot')
        definitions = None
        if args.kind == "permission-registry":
            if not getattr(args, "definitions", None):
                raise ValueError("permission-registry requires source definitions")
            definitions = json.loads(args.definitions.read_text())
            names = sorted(row["name"] for row in definitions["definePermissions"])
            if (not names or len(names) != len(set(names)) or
                    any(re.fullmatch(r"ohos\.permission\.[A-Za-z0-9_.]{1,240}", name) is None for name in names)):
                raise ValueError("invalid or duplicate source permission names")
            names_path = args.output / "permission-names.txt"
            names_path.write_text("\n".join(names) + "\n")
            evidence.update(definitions=str(args.definitions.resolve()),
                            definitions_sha256=digest(args.definitions),
                            names_sha256=digest(names_path), source_permission_count=len(names))
        elif args.kind == 'native-gap-abi':
            if not getattr(args, 'definitions', None):
                raise ValueError('native-gap-abi requires actual final-image ABI definitions')
            definitions = json.loads(args.definitions.read_text())
            validate_native_abi(definitions, args.device, args.arch)
            evidence.update(definitions=str(args.definitions.resolve()),
                            definitions_sha256=digest(args.definitions))
        elif getattr(args, "definitions", None):
            raise ValueError("source definitions apply only to the permission-registry probe")
        validate_elf(args.probe, args.arch)
        evidence.update(archive=str(args.archive.resolve()), archive_sha256=digest(args.archive),
                        probe=str(args.probe.resolve()), probe_sha256=digest(args.probe))
        if getattr(args, 'boot_evidence', None):
            manifest, boot = validate_boot_archive(args.boot_evidence, evidence['archive_sha256'],
                args.arch, args.device, args.target, getattr(args, 'boot_id', None))
            env = boot['test_environment']
            if args.kind == 'project-quota' and (boot.get('purpose') != 'acceptance' or
                    any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                        'diagnostic_assistance', 'diagnostic_power_button'))):
                raise ValueError('quota enforcement must use the original unmodified packaged kernel')
            current = command(['ps', '-p', str(env['qemu_pid']), '-o', 'command=']).strip()
            if current != env['qemu_command'] or env['qmp_socket'] not in current:
                raise ValueError('actual host process no longer owns the original private QMP VM')
            if args.kind == 'native-gap-abi' and (args.definitions !=
                    Path(env['freshly_extracted_directory']) / 'native-gap-abi-image.json' or
                    evidence['definitions_sha256'] != boot['initial_package_file_sha256'].get('native-gap-abi-image.json')):
                raise ValueError('Native ABI definitions are not the actual checked new package member')
            evidence.update(package_manifest=manifest, boot_evidence=str(args.boot_evidence.resolve()),
                boot_evidence_sha256=digest(args.boot_evidence),
                archive_binding='actual_live_owned_boot_and_initial_full_archive_inventory')
        else:
            evidence["package_manifest"] = validate_archive(args.archive, args.arch, args.device)
        command([args.hdc, "tconn", args.target])
        validate_identity(shell("id -u; param get const.product.devicetype; uname -m"), args.arch, args.device)
        if getattr(args, 'boot_id', None) is not None:
            actual_boot_id = shell('cat /proc/sys/kernel/random/boot_id').strip()
            if (re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', actual_boot_id) is None or
                    actual_boot_id != args.boot_id):
                raise ValueError('root probe is not on the enclosing fresh kernel boot')
            evidence['boot_id'] = actual_boot_id
        # mkdir must be atomic, without -p: an existing guest run is an error.
        marker = "__OHOS_PROBE_CREATED_" + run_id
        if shell("umask 077; mkdir " + shlex.quote(remote) + " && printf '" + marker + "\\n'").strip() != marker:
            raise ValueError("could not create a fresh guest run directory")
        command([args.hdc, "-t", args.target, "file", "send", str(args.probe.resolve()), remote + "/probe"])
        actual_sha = shell("chmod 700 " + shlex.quote(remote + "/probe") +
                           " && sha256sum " + shlex.quote(remote + "/probe")).replace("\r", "")
        if actual_sha.split() != [evidence["probe_sha256"], remote + "/probe"]:
            raise ValueError("guest probe content differs from the recorded executable")
        if args.kind == 'native-gap-abi':
            current_syscap = shell('sha256sum /system/etc/syscap.json').split()
            if current_syscap != [definitions['actual_syscap_sha256'], '/system/etc/syscap.json']:
                raise ValueError('actual guest SysCaps differ from the whole final-image ABI contract')
            evidence['actual_guest_syscap_sha256'] = current_syscap[0]
        if args.kind == 'permission-registry':
            command([args.hdc, "-t", args.target, "file", "send", str(names_path.resolve()), remote + "/permission-names.txt"])
            observed = shell("sha256sum " + shlex.quote(remote + "/permission-names.txt")).split()
            if observed != [evidence["names_sha256"], remote + "/permission-names.txt"]:
                raise ValueError("guest permission name input differs from source definitions")
        quota_device = None
        if args.kind == 'project-quota':
            mounts = shell('cat /proc/mounts')
            quota_device = data_device(mounts)
            mounts_path = args.output / 'actual-mounts.log'
            mounts_path.write_text(mounts)
            evidence.update(quota_device=quota_device, actual_mounts_sha256=digest(mounts_path))
        code = parse_exit(shell(probe_command(args.kind, remote, run_id, quota_device), timeout=90), run_id)
        evidence["probe_exit_code"] = code
        for name in ("stdout.jsonl", "stderr.txt"):
            # These generated test artifacts are preserved even on probe failure.
            content = shell("cat " + shlex.quote(remote + "/" + name))
            (args.output / name).write_text(content.replace("\r", ""))
        log = (args.output / "stdout.jsonl").read_text()
        evidence["log_sha256"] = digest(args.output / "stdout.jsonl")
        evidence["result"] = verify_result(args.kind, log, args.arch, run_id, code, definitions, args.device)
        if getattr(args, 'boot_id', None) is not None:
            if shell('cat /proc/sys/kernel/random/boot_id').strip() != args.boot_id:
                raise ValueError('root probe guest rebooted/changed during execution')
            evidence['kernel_boot_id_unchanged'] = True
        evidence["status"] = "pass"
    except (OSError, ValueError, TypeError, KeyError, tarfile.TarError) as exc:
        evidence["failures"].append(str(exc))
    finally:
        (args.output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("bitmap", "userid", "vibrator-hdi", "permission-registry", "audio-suite", "bpf", "binder-sender", "rs-objects", "screen-modes", "project-quota", "native-gap-abi", *GRAPHICS_KINDS), required=True)
    parser.add_argument("--definitions", type=Path, help="source permission definitions or actual final-image Native ABI table")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--arch", choices=tuple(ARCHES), required=True)
    parser.add_argument("--device", choices=("phone", "2in1"), required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument('--boot-id', help='exact boot ID supplied by the enclosing owned-VM suite')
    parser.add_argument('--boot-evidence', type=Path,
                        help='reuse this live owned boot\'s complete checked archive inventory (requires --boot-id)')
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hdc", default=os.environ.get("HDC", "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"))
    args = parser.parse_args()
    evidence = run_probe(args)
    print(json.dumps({"status": evidence["status"], "run_id": evidence["run_id"],
                      "failures": evidence["failures"], "evidence": str(args.output / "result.json")}, indent=2))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
