# 7.0 representative package R8: build and behavior evidence

R8 is a newly built and booted first artifact. Its narrow regressions passed, but
the complete C++/ArkTS 1.1 audit gate failed. This package does **not** authorize
building the remaining five packages or claiming all API 26 capabilities work.

- Package: `/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`
- SHA-256: `63a8b094d26e09d2bce7e94b6ada9951e17d261cd1e8a50d34abba53a7409191`
- Build environment: local Docker image `ohos-qemu-build-env:7.0-release-gn-qemu-user`, source volume `ohos-qemu-7_0-release-source`, output volume `ohos-qemu-7_0-release-out`, fixed 7.0 manifest `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`, `arm64_virt` phone, four build jobs; no GitHub CI. Build command: `DEVICE_TYPE=phone PRODUCTS=arm64_virt BUILD_JOBS=4 SKIP_APT=1 SKIP_REPO_SYNC=1 PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8 bash scripts/run_2in1_full_build_docker.sh` (with the pre-resolved M144 and other dependency-cache environment paths). Full build log is `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/first-rs-objects-arm64-phone-build-08c.log`.
- Test environment: fresh extraction from this archive on macOS arm64, `qemu-system-aarch64` with HVF, four vCPUs, 4 GiB RAM, 1280×800 virtio GPU; `arm64_virt` phone, HDC `127.0.0.1:51693`, boot ID `ff277738-8460-45ae-85a2-30fb4e3e6430`, no external keepalive. The exact QEMU command and image paths are recorded in `boot/boot.json` under the runtime root below.
- Full new-package validation command: `QEMU_TEST_PYTHON_ENV=/tmp/ohos-capability-tests-pvk51rjh OHOS_NATIVE_BINDINGS=/Volumes/PSSD/code/ohos-rs/ohos-native-bindings QEMU_TEST_SDK_HOME=/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0 bash scripts/validate_packaged_qemu.sh --package-archive /Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/openharmony-qemu-arm64-arm64_virt-phone.tar.gz --package-directory /Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/openharmony-qemu-arm64-arm64_virt-phone --evidence-output /Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/first-artifact-behavior.json`.
- Evidence: `/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/first-artifact-behavior.json`; per-probe evidence and logs in `/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261008-r8/openharmony-qemu-arm64-arm64_virt-phone-runtime-24sgewts`; validation log `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/first-rs-objects-arm64-phone-runtime-08c.log`.

The fresh guest booted, suspended/resumed and reached home. ArkWeb ordinary-app
DOM/Canvas/WebGL, independent Vulkan native/WSI/window, UDMF exit, native ABI,
RS object boundaries, certificate manager, virtual vibrator HDI, AudioSuite,
and permission-registry probes passed. Camera passed two ordinary-app live
preview cycles (four colored regions each) and four nonblank JPEG callbacks
with positive timestamps; video and advanced camera modes were not tested.
The ordinary-app ArkTS reflection confirmed the three repaired accessibility
enums and exact member values. `ohos-native-bindings` passed 32 modules and 102
cases, including QoS, JSVM, vibrator, and XComponent.

The complete audit still fails. The original R8 verifier reported 61/291
requirements closed; a read-only replay of the *same* archive and boot after
fixing a verifier-local phone/2in1 variable collision reported 62/291 closed,
229 unresolved (152 ArkTS runtime exports, 75 behaviors, two permissions):
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/diagnostic-r8-gap-closure-after-device-fix.json`.
That replay is diagnostic only: the source verifier now differs from R8's
frozen build inputs, and it is not a new-package gate pass. The remaining
five-package matrix has therefore not started. After the verifier correction,
`/tmp/ohos-capability-tests-pvk51rjh/bin/python -m unittest discover -s
ci/capability-audit -p 'test_*.py' -q` passed 796 host tests; host tests do
not replace a new archive boot or close the remaining runtime gaps. The
independent `python3 scripts/verify_first_artifact_gate.py --archive <R8 archive>
--evidence <R8 first-artifact-behavior.json> --repository "$PWD" --product
arm64_virt --device-type phone` correctly rejected the failed evidence.
