# 旧 feature 分支 11 提交审计 374

**未发现当前 a0d6215 缺失的独有真实代码；这 11 个旧提交不需要重放。** 逐 blob/hash 与语义 diff 检查了组件、构建入口和 ABI 校验，不执行候选、测试或资源。

| 原提交 | 当前结论与具体证据 |
| --- | --- |
| 38813418 | 77/105 blobs retained exactly; 26 current upgrades. Two old master-only ArkWeb patches were intentionally removed by 203762a for unified release. JSVM/QoS/vibrator/armv7a/VPN/pointer components remain. Current device-type dispatcher delegates the full builder ordered plan. |
| 8aa4575 | 19 obsolete overlays remain deleted. Four current build/package/check entrypoints retain component migration with stronger source/dependency/runtime gates; restoring overlays would regress design. |
| 58368bf | Four docs/CI files evolved. Current profile/smoke tests retain component roots and QoS/vibrator/M144/full-profile assertions, replacing empty marker libraries with actual ELF fixture generation. |
| fdd7fc9 | 0008 pointer-compression patch exact; current JSVM apply includes it. Current release V8 builder retains ARM compression/shared-cage off and i386 multilib host preparation. Old master seed/sync builder replaced by locked release entry. |
| 49012e5 | Mount-array support, matrix exact package count and six packaging-capability predicates retained/upgraded. Current matrix additionally requires actual runtime per archive and representative-first gate; do not restore metadata-only matrix. |
| 4cd91d5 | Both files exact: QoS README and qos_auth.patch retain x86 linux/compat.h fix. |
| 051ddaa | 0004/0005 x86 compat patch blobs exact, still named in qos_manager/apply.sh before ARM32 patches. |
| f9633f6 | Five blobs exact: JSVM0009/0010, QoS0006/0007, QoS apply. Current JSVM apply wires both and ci/standard-vpn retains native ARM32 pointer assertions. |
| 3c1efa9 | Six blobs exact: JSVM0011+apply+README, vibrator BUILD fix, ArkWeb0017/0018. Current artifact checker/build retains __h/ABI1 and adds actual GN args/header/patch hashes plus Intl/embedded ICU checks. |
| 1483470 | verify_runtime_elf_contract.py and ci/make-elf-fixture.py exact. Current packager and device validator still invoke real ELF contracts for vibrator export and JSVM/V8, with retained CI/workflow hooks and broader checks. |
| 19fba6d | Exact Bash3.2-safe PACKAGE_MOUNT_ARGS empty-array expansion remains in current runner, despite subsequent surrounding additions. |

两个缺席文件不是遗漏：38813418 原有 ArkWeb 0001-remove-v8-presubmit-gate-from-build.patch 和 0005-enable-ohos-third-party-gn-targets.patch 已在 203762a 因 unified 7.0 release 本身自带对应行为而明确删除。当前 README/apply 一致，原删除 diff 保存在本目录。不能恢复旧 master-only 补丁。

当前 build_m144_v8.sh 进入 run_m144_release_build_docker.sh 的 locked release graph。ARM compression off/i386 multilib、OpenHarmony __h/ABI1 均在，且实际 GN 参数/public header/patch 内容 hash 与 Intl/内嵌 ICU 检查更严格。QoS compat/ARM32、JSVM destructor、vibrator export 与原 ELF checker/fixture 都保留，full builder 仍调用其组件。当前 matrix 还需新代表包实际运行门槛，不可回退为旧 metadata-only 全矩阵。

Bash3.2 安全空数组展开仍在当前 runner 第 547 行。每提交 retained/upgraded/deleted 分类、文件 SHA、当前关键语句行号在 DECISION.json/INPUTS.json；原 patch 与各自当前差异完整保存。

旧 network scratch 已释放，本任务未访问该旧工作树。root 可备份清理；本次只写独占审计目录，无 Git mutation、测试、编译或外部资源。代码已保留不等于新包行为验收已通过。
