# Exact SDK39 NativeStrip receipt

Base `0f1f4eef8789f74cc07d3b249dabb17673b1ec98`. Only the newly authorized `batch_system_sdk_native_strip.py`, its dedicated test and this documentation are added. Existing system/live-inputs wrappers, shared/core scripts, original SDK03 evidence, HAP, DSOs and source/out are untouched. This child ran no actual strip, SDK/native build, signature or VM operation.

## Actual read-only failure diagnosis

`actual-sdk03-read-only-difference.json` preserves host reads of the original SDK03 HAP, pre-HAP DSOs and actual Hvigor stripped intermediates. Original report SHA is `e4571778786fe5181eb1a0015d6168d2ed4b4c3f3ba60609d7a50f04f6c73276`; HAP SHA is `d223d7dacfcf743329aef8af034ab07d2ebbc1988c74ad0de4cbb96535790a27`.

| Member | Original | Actual HAP | Read-only comparison |
|---|---|---|---|
| libliveinputaudit.so |15072B, `ff08c0b52f7e7ed736916a88b3cbc5422d883f0497f912a9afb8da845940695c`|6744B, `34cdb84e824701bc8e736b763337cb8f74bda0bca496510da6ce219e6112b516`|same complete program headers and allocated sections; only `.comment`, `.debug_*`, `.symtab`, `.strtab` removed and `.shstrtab` rebuilt|
| libc++_shared.so |1262248B, `bff501a19fadbc9a006d7f26a9bf62137cb5ec124959d3fdb701e9278f3df274`|same exact bytes|already contains no `.symtab`, `.strtab`, `.comment` or debug sections|

Each actual `intermediates/stripped_native_libs/default/arm64-v8a/` file equals its HAP member byte for byte. The original successful Hvigor log records `Finished :entry:default@DoNativeStrip`. These observations support the NativeStrip diagnosis but do **not** prove that a new exact replay succeeds. No ELF similarity or arbitrary replacement hash is an acceptance rule.

## Root execution

```sh
python3 ci/capability-audit/batch_system_sdk_native_strip.py recheck \
  --sdk /ohos/prebuilts/ohos-sdk/linux/26.0.0/native \
  --native /ABS/SDK03/live-inputs/entry/libs/arm64-v8a/libliveinputaudit.so \
  --hap /ABS/SDK03/live-inputs/entry/build/default/outputs/default/entry-default-unsigned.hap \
  --member libs/arm64-v8a/libliveinputaudit.so \
  --sdk-evidence /ABS/SDK03/evidence.json --output /ABS/NEW-native-strip-recheck
```

`--sdk` is the **native root**, not its26.0.0 parent. Root must run this serially under its real Linux read-only SDK lease after source prepare exits. The output directory must not exist and must be outside the SDK. No original file is overwritten. Inputs are hash checked again after execution; no HAP rebuild, DSO replacement, policy adjustment or original-report rewrite occurs.

The script requires actual `native/oh-uni-package.json` to identify Native API26/26.0.0.39/Release and its raw SHA to match the original `native_builds` metadata read. SDK105 is rejected. The original compiler root must be the same SDK. SDK filesystem read-only status and canonical tool/metadata paths within that SDK are checked. `llvm-strip` must have pinned SHA `78bee3733d321304ee24d068840878a4413cc4ac814c6beab5705da14e65a7af`, the same unchanged tool pinned by `scripts/verify_m144_hap_native_transform.py`.

The tool is invoked for its actual `--version`, then for **every** main/runtime library as `[original-sdk/llvm/bin/llvm-strip, fresh-work-copy, '-o'+fresh-output]`. Original native and Hvigor commands must all have exited0 for the selected project; their raw logs and completed NativeStrip task are checked. Every native HAP member in the ABI must be accounted for by the main DSO and `native_build.runtime_libraries`; extra/missing/other-ABI members fail. Runtime libraries are replayed even when the expected transformation is a no-op.

`<output>/receipt.json` initially fails and receives `status='pass_exact_SDK_NativeStrip_ONLY'` only if every actual strip exit is0 and every resulting file equals its current HAP member **in full bytes**. Scope is `exact_original_SDK39_NativeStrip_NOT_signing_or_guest_acceptance`; runtime and first-artifact gate flags remain false. Failed commands/mismatches retain a failed receipt and all available raw artifacts. Fresh failure output is not overwritten on retry.

The directory retains the actual executed script copy; original SDK report/logs; original SDK tool and metadata byte copies; recorded original/canonical SDK paths with before/after read SHA; original native/runtime copies; work copies; actual transformed outputs; actual argv, exit, duration and separate stdout/stderr SHA/log files; HAP/member SHA/size; complete original/stripped ELF diagnostics. ELF diagnostics are supplementary. Empty successful compiler/strip stdout/stderr is valid and remains hash checked.

## Independent wrapper API

```python
caller['native_strip_receipt'] = {'path': '/ABS/recheck/receipt.json', 'sha256': actual_sha}
from batch_system_sdk_native_strip import verify
proof = verify(caller, native_build, original_binary)
```

`caller` retains its existing `sdk_project`, `sdk_evidence` and `unsigned_hap` descriptors. `native_build` must be the exact selected dictionary in the unchanged original SDK report. `original_binary` is the original pre-HAP DSO or a byte-identical private capture; its adjacent runtime libraries must also remain byte-identical to their recorded originals. Root may copy the **complete recheck directory** and point the descriptor at the copied receipt; internal retained artifacts are relative and original executed argv remain unchanged. Copying just the JSON is insufficient.

`verify` runs no subprocess and opens no Linux SDK/tool path on the host. It independently rehashes retained actual script vs current verifier, pinned tool, actual metadata/version vs original SDK read, original report/commands/logs, main/runtime source copies and actual strip outputs. It requires exact expected original/work/output roles and official argv, unchanged successful command set and successful version log, exact original SDK HAP identity, complete library coverage and current HAP member equality. Actual tool provenance remains the recorded real Linux read/execution plus its retained bytes; no host reread of `/ohos` is claimed. Different HAP resources cannot borrow the same native members, and changing a summary digest, tool, metadata, script, argv, log or result cannot pass.

The return preserves status/scope and receipt descriptor, SDK version/metadata SHA, pinned strip tool SHA, original native and HAP SHA and a `libraries` mapping with each original SHA, actual packaged SHA/size. `runtime_validated` and `first_artifact_behavior_gate_passed` remain false. Root owns adding this proof to `sdk_caller`, private capture, signing and runtime acceptance.

## Host tests and remaining work

`host-tests-01.log`:17 passing pure-Python mock/output/receipt tests in0.177s (retaining process0.26662s), SHA `0aa1128d42f550d8417446e084fb6e01ee6c4f0b740afdaaf50a3aa74238fc19`. `host-evidence.json` contains the exact command and source SHA values. Counterexamples include wrong SDK version/tool/read-only mount, missed runtime/ABI, merely similar ELF, failed/absent NativeStrip, changed HAP resources, altered tool/script/metadata/argv/log, runtime change, missing/changed transformed bytes and private-capture/copy semantics. Tool invocations are explicit mocks using synthetic ELF bytes. No mock receipt is retained as real SDK evidence.

Root must still execute the CLI against actual SDK39, retain real success or failure unchanged, independently call `verify`, and continue the existing complete representative-package/runtime gate. No requirement is closed by this batch.
