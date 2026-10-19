# 整合后 system 剩余 9 项只读分类

依据主树 `721798e1159da9b213c3f92d5a3c17207e505fe6`；所读关键文件字节均与此提交一致。仅取373 system11中除Calendar/Knowledge的9个原ID；新增完整闭合0。**9项未闭环不等于9项没有实现。**

| 原 ID（均为 behavior:） | 当前整合代码 | 仍需补齐/诚实 unknown | 关键文件与行号 |
| --- | --- | --- | --- |
| access-token-api26-kernel-abi | 已有锁内bitmap快照、task user-id ioctl、普通/自定义AppSpawn在drop-root前真实setter、SPM成功版本握手，active build已接线 | 待新包root/normal真实ABI、权限/并发/恢复及真实HAP父子token/UID/account映射。增强SPM不是因optional不支持就必须新增；raw ABI探针不关闭全部AccessToken | `scripts/build_standard_qemu_in_docker.sh:3230`；`access_token_abi/0001-query-real-permission-bitmap-under-lock.patch:96`；`ci/capability-audit/verify_access_token_results.py:50` |
| native-child-process-phone-boundary | 已有跨DSO参数、bounded Parcel/config、retain-before-dispatch/一次回调修复，active build接线；完整disabled C/ArkTS protocol存在 | 待新包enabled真实child/FD/数据/回调退出和父子身份，同时重验disabled。不能按旧文字断言缺801：当前ArkTS要求801，C native ErrCode要求16010004，不能混改；旧fixture不是新包通过 | `scripts/build_standard_qemu_in_docker.sh:3042`；`ci/capability-audit/verify_child_default_profile_results.py:12,36`；`fixtures/child_default_profile_diagnostic_02/provenance.json:2` |
| graphics3d-scene-manager-unavailable | 已有真实plugin registry retry、engine初始化/回滚和JS queue failure寿命修复，active接线 | 当前新包Scene.load/render/destroy/recreate、坏asset/失败retry与真实DSO来源待验。已修源码问题不是完整根因已证明，余下实现需求unknown | `scripts/build_standard_qemu_in_docker.sh:3056`；`patches/common/foundation/graphic/graphic_3d/scene_startup/README.md:3` |
| msdp-device-status-mock-or-missing-clients | 已有真实SensorHDI/算法/public still、共享订阅和worker寿命；QEMU禁mock、sensor flag及两组件active | 明确relativeStill仍unsupported；全部声明的client/modality/model未由still子集覆盖。物理immobility准确性及全client缺口需真实产品集合核对；待外部challenge/普通HAP/并发订退/death/timeout恢复 | `scripts/build_standard_qemu_in_docker.sh:3480`；`patches/lib/sensor_features.py:6`；`public_still/README.md:20`；`ci/capability-audit/batch_system_verify_live_inputs.py:97` |
| session-manager-profile-gap | phone主动加入SessionManager，启用SceneBoard/unified render、signed preinstall/runtime/unlock接线 | 待新包实际SDK/image canIUse与service一致，公开window/session寿命、适用PiP/FloatingBall/FloatView与UI/进程恢复。声明、Home可见不等于完整实现通过；更多具体缺实现unknown | `patches/phone/product_profile/apply.py:305`；`patches/lib/sceneboard_profile.py:66,103`；`scripts/build_standard_qemu_in_docker.sh:3023` |
| advertising-service-provider-missing | 源清单有ads_framework，framework/provider审计存在；未找到补齐真实provider/配置的当前补丁和active安装绑定 | 需真实service/UI/API provider及准确四entrypoints/providerApiAbilityName/签名安装和真实load/display/callback边界。是否由外部source/image另供unknown；未把旧Demo缺失当本次镜像测量 | `ci/capability-audit/audit_system_bundle_providers.py:166`；`ci/capability-audit/known-findings.json:1950` |
| device-attest-uninitialized | 有锁定upstream device_attest及历史可达SA5501，不是整套service不存在；未找到当前OEM adapter/产品信任配置修复 | 需真实OEM identity/key/信任与处理链，实际ticket与结果；不能伪造INIT→pass。当前外部OEM输入/镜像配置unknown，本轮没读image | `scripts/openharmony_7_0_release_source_lock.json:1654`；`ci/capability-audit/known-findings.json:1754` |
| security-guard-empty-model-config | upstream SecurityGuard/service存在，当前repo未找到真实模型配置/collector补齐；保留的旧model fixture为空 | 需支持的真实model/config/data path、可验证result与权限/错误/重启边界。旧modelcfg[]不是当前image dump，外部是否另供模型unknown | `scripts/openharmony_7_0_release_source_lock.json:549`；`docs/capability-audit/runtime/arm64-phone/system-config/security-guard-model.json:1`；`ci/capability-audit/known-findings.json:2679` |
| app-domain-verification-extension-missing | 当前记录已纠正：optional DSO缺失时upstream VerifyTask/VerifyHttpTask验证和refresh fallback真实存在 | 不能按缺soname断言缺实现。HTTP/HTTPS ownership/签名/refresh/撤销及ConvertToExplicitWant空TargetInfo后的真实路由待验；是否需新增extension/转换实现仍unknown | `ci/capability-audit/known-findings.json:3251`；`docs/capability-audit/native-arkts11-gap-ledger.json:4656` |

分类合计：**5项已有实质修复及active接线、待完整验收；3项当前仓库未提供对应provider/model修复或集成；1项upstream fallback已存在、完整行为/路由仍unknown。** 这不是“明确还有3项全部实现不存在”，也不能从该9项推导全82项纯缺实现总数。MSDP的relativeStill是另外保留在其广义ID内的明确未支持功能，不新增ID计数。

`NINE_ID_REVIEW.json`给出逐ID具体当前实现、known/unknown、验收条件与所读关键文件SHA。`SEARCHES.json`仅保存四个轻量repo搜索结果，用于限定“没找到对应修复”的范围；不含外部source或运行产物。前述旧fixture/README/known-findings仅为来源，不计当前运行成功。

只读主树；未继续使用旧worktree、未访问source/out、未import/执行候选或tests、未启动SDK/编译/签名/crypto/Docker/VM/HDC/QMP，未改Git或产品。此目录冻结后停止写入。
