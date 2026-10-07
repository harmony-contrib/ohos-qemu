# 7.0 representative package R7: build and behavior evidence

This is an intermediate **failed** first-artifact gate, not approval to build
the other five packages. It records the newly packaged artifact tested before
the full matrix, including its successful narrow regressions and remaining
complete-audit failure.

- Package: `/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r7/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`
- SHA-256: `90624926d60d06019d7608cebb10abf59138bec030a0156bd92fa2127cd665ff`
- Build: local Docker with fixed `OpenHarmony-7.0-Release` manifest `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`, product `arm64_virt`, device `phone`; no GitHub CI.
- New-archive test environment: macOS arm64, QEMU aarch64/HVF, 4 vCPU, 4 GiB RAM, 1280×800 virtio GPU, guest account 100, HDC `127.0.0.1:61019`, boot ID `b392f9af-1ec8-47e4-a712-88b4c37a7c4c`, no external keepalive. The VM was freshly extracted from the archive.
- Commands: `bash /Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/run-first-rs-objects-arm64-phone-07.sh` (sets Docker dependency paths, runs `scripts/run_2in1_full_build_docker.sh`, records `shasum -a 256`, then runs `scripts/validate_packaged_qemu.sh --package-archive ... --package-directory ... --evidence-output ...`). The independent gate command is `python3 scripts/verify_first_artifact_gate.py --archive ... --evidence ... --repository "$PWD" --product arm64_virt --device-type phone`.
- Full suite evidence: `/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r7/first-artifact-behavior.json`; source test logs and per-probe evidence remain in its `openharmony-qemu-arm64-arm64_virt-phone-runtime-_2okknjh` directory. Build log and archive checksum are under `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/` with suffix `-07`.

The new package boot, default suspend/wake, home, Native ABI, RS object
boundaries, UDMF/DSO exit, certificate boundaries, ArkWeb, Vulkan native/WSI
and visible window, permission registry probe, and virtual Vibrator HDI probe
passed. Camera passed two ordinary-user preview cycles with four colored
regions in each compositor screenshot, four nonblank JPEGs, real callbacks and
positive timestamps. `ohos-native-bindings` passed all 32 current modules and
102 cases with zero failures, including QoS, JSVM, Vibrator and XComponent.

The complete suite still reported `first_artifact_behavior_gate_passed=false`:
the final gap-closure verifier attempted to read a nonexistent `device` field
from ArkTS application evidence, and the outer PowerMgr cleanup interpreted an
already-restored timeout as a failure despite the original policy readback.
Both verifier defects have since been corrected in the repository, invalidating
R7's build-input hash for any future gate pass. An offline diagnostic replay
before the permission-profile correction also showed 303 audited requirements,
only 56 closed, with 247 still unresolved. A fixed-source permission audit
subsequently identified 12 phone-only false requirements whose source policy
explicitly restricts them to 2in1/TV; the resulting ledger is now different
from R7's frozen test inputs. These corrections are not a runtime capability
pass and require a new representative package and fresh validation.
