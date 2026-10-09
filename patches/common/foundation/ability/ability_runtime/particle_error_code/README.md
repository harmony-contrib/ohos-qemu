# FA particleAbility ErrorCode

User-approved additive NAPI repair for pinned OHOS 7.0 Release ability_runtime
`6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`. API26's
`@ohos.ability.particleAbility.d.ts` declares exactly
`ErrorCode.INVALID_PARAMETER = -1`, available since API7, FA-only.

Export that object without copying featureAbility's unrelated constants. All
existing module initializers, lifecycle, error paths, permission checks and IPC
remain unchanged. Registration allocation/property failures return failure;
no partial object is published. No new source file, dependency or GN target.

Maintenance plan: NAPI compatibility repair. Read ability_runtime/AGENTS.md,
particleAbility/native_module.cpp and BUILD.gn, ability_business_error.h,
ability_runtime_error_util.h and services/abilitymgr/CLAUDE.md. Do not modify
published errors (including Stage's 401), lifecycle or service policy. No skill
or service implementation change is needed.

Host patch/registration checks are not FA guest evidence. Compile the real NAPI
module and validate an actual FA caller plus Stage regression on a fresh archive
before closing this gap or starting the remaining five packages.

2026-10-09: three host regression cases pass (including 128 repetitions of all
four NAPI failure points under ASan/UBSan). Applying twice to the actual pinned
source copy passes. `compile_public_module_registrations.py --components
foundation/ability/ability_runtime/particle_error_code` compiles the real
registration translation unit with cached ARMv7a/ARM64/x86_64 product commands,
read-only source/out mounts and unchanged source hashes. Evidence:
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/particle-registration-three-abi-r21-01/evidence.json`.
This is not full linkage or guest validation; FA/Stage runtime remains pending.
