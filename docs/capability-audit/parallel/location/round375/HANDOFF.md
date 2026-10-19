# 定位 / 电话 round375 交接（2026-10-19）

本批提供真实 ArkUI GN CFI 修复及完整 canonical checkout 工具后继。
源码/主机检查已完成；新包原生编译、链接、guest 和 22 项能力验收仍由 root 执行。

## 产品修复与 root 接线

新增组件 `patches/common/foundation/arkui/ace_engine/ui_extension_identity_cfi/`，
upstream 仅修改以下两份已从真实 source volume 封存的完整文件：

- `foundation/arkui/ace_engine/frameworks/core/components_ng/components.gni`
- `foundation/arkui/ace_engine/build/BUILD.gn`

实际缺口并非全局关闭 CFI：sanitizers.gni 的 `use_cfi` 默认为 `!is_host_product`，
但实际 `build_component_ng` source-set 没有 sanitize，最终 libace_compatible 原
sanitize 块也只有 integer/bounds。真实 ui_extension/BUILD.gn 已确认
`build_component_ng("ui_extension_pattern_ng")` 包含完整 identity CPP；354 的真实
Clang 命令因此有 ThinLTO/noRTTI，无 CFI。私有 native admission 明确要求两 carrier
原 GN whole TU CFI/LTO/noRTTI，不能改旧命令或将实际缺 flags 直接记为通过。

组件仅对 current_os=ohos、platform=ohos、component_name=ui_extension_pattern_ng
启用 cfi/cross_dso，并在最终 libace_compatible 原 sanitize 块启用同样两项。
其他组件、ohos_ng、host/cross-platform 不变。use_cfi、ASan/TSan、debug 和已有
integer/bounds 配置均保留。配置采用既有 sanitizer machinery；ARMv7/ARM64/x86_64
实际支持必须分别由真实 GN/编译/最终链接证明，不能从源码推定六包通过。

root 需要将新组件加入共享 patch apply/build 入口，紧邻现
`ui_extension_identity_diagnostics`。prepare 后调用新 verify_source.validate(root,
require_patched=True)，两文件必须完整后态；任何一半应用或未知修改直接拒绝。
我未编辑共享入口、source/out、SDK/签名，也没有运行实际 GN/编译/VM。

原始真实 source/out 证据位于统一 validation BASE 下：
`r60-GN-source-vector-375-01`、`r60-GN-target-vector-375-01`、
`r60-GN-extension-vector-375-01`。这些是旧 prepare 上下文的只读观测；root
Owner35 已严格关闭，不能当 375 prepare、新编译或新包通过。

## 完整后继 kit

`ci/capability-audit/batch_location375_kit.py` 是有界纯文件组装器，不启动任何资源。
117 个原输入由 source-lock.json 固定，最多 4 MiB/文件、16 MiB 总量。原368、370、
372、354、16目录均保持原字节。新增 kit 包含完整 inventory、compile、raw GN
exporter、runtime、role exporter、独占 Owner35 support 和全部实际私有依赖，
不再只交四文件 overlay。旧manifest另存 provenance，所有活动manifest固定真实
新成员及 support SHA。协议与内部目录名保留；successor375明确记录新身份。

最终冻结 kit：

`/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/round375-location/kit03/`

根 manifest `SOURCE_MANIFEST375.json`：
`76a8bfd4828beb546277b3897f90971c22d6b7eb30559c61169c7b3a10421d21`

source lock SHA：
`e9644c398cd6e34428bb5fff8571cf323168b5ee5c4d1da8a68f09884643c674`

新的 Owner35 HERE 来自自身新 kit 位置，QA_ROOT 指向唯一主 checkout。
`clean` 还验证 exact clean HEAD 和 `codex/ohos7-integrated-development`；不会使用
旧 detached F 工作区，也不为旧包设置 sourcepoint 豁免。所有原 global lock、35/48
marker、daemon/CLI 身份及严格清理逻辑保留。不得在这些 CLI 外再嵌套持有同一全局 lease。

```sh
PY=/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python
R=/Volumes/PSSD/code/ohos-rs/ohos-qemu
K=$R/.tmp/parallel-capability-20261016/round375-location/kit03
PIN=76a8bfd4828beb546277b3897f90971c22d6b7eb30559c61169c7b3a10421d21
"$PY" -B "$R/ci/capability-audit/batch_location375_kit.py" \
  --verify "$K/SOURCE_MANIFEST375.json" --manifest-sha256 "$PIN"
"$PY" -B "$R/ci/capability-audit/batch_location375_kit.py" \
  --verify "$K/SOURCE_MANIFEST375.json" --manifest-sha256 "$PIN" --print-private-bindings
```

第二条输出八个真实 runtime private_sources、两个 exporter private_pins、实际
private_contract descriptor、六个实际入口路径。`private-bindings03.json` 已保留同样
输出。这是私有源码字段，不是完整 ready/config/receipt：必须与真实同一新commit的
package/profile/helper/tool/archive/boot/native证据组合，旧2f0/17-06包不可重标新源码。

入口均可直接用新 kit；原CLI全保留：

- inventory：`$K/F-location-inventory-fix354-draft/run_inventory354.py`，`--here "$K"`
  `--qa-root "$R"`，wrapper-manifest-sha256取此新子目录实际manifest SHA。
- observe/compile：`$K/F-location-compile-query368-draft/run_location_compile129.py`，
  同样显式 here/qa-root；compile必须取真实成功且清理关闭的同一后继 observe。
  新完整 `-t commands -s` query、原raw stdout、实际Clang/source/-o绑定保留；ArkUI
  缺 CFI 时仍拒绝。仅允许真实 flat lib64 或实际 lib64/platformsdk 单basename。
- raw GN diagnostic：`$K/F-location-GN-export370-draft/run_GN_export370.py`，显式
  `--here "$K"`、新子manifest SHA、真实 native source revision及有限路径。
- offline role image：`$K/prepare_location_roles16.py`，实际 spec中的私有字段取新
  bindings。镜像哈希/唯一inode/alias/init/DSO全部必须真实。
- runtime trace/switch：`$K/run_gnss_existing_trace_steps16.py` 与
  `$K/run_location_switch_bootstrap16.py`，真实新包配置及 root VM/HDC lease 必需。
  exporter/runtime同样增加有限 lib64/platformsdk路径；绝不将basename、flat路径或
  staging-derived路径当实际 loaded map。设备/inode/完整bytes/进程代际/角色连接保留。

最初kit01两组host失败仅为缺原先测试fixture及 relocated shared-parser测试路径；
失败日志保留。kit02补齐完整fixture，测试明确使用canonical真实shared-parser路径。
kit03的112个已有成员与经过296项host测试的kit02全字节相同，只额外封存真实组装器
及source lock副本，不改变任何执行模块。最终根manifest包括114个成员并拒绝未列入文件。

## 检查与后续验收

- 完整 kit：compile 60、GN exporter 21、inventory 39、runtime 149、role exporter 12、
  Owner/common 15，总296项主机检查通过。日志/argv在 round375-location/host-results02.json。
- 新增 tracked 检查：18项组装/来源/路径/边界 + 11项真实 GN source apply/replay及实际CLI检查通过。
- 组装器不含subprocess/Git/SDK/Docker/VM API；所有检查仅私有tempfile/mock及源码补丁scratch。
  tracked kit测试在未安装显式私有前驱的独立checkout中明确skip，不虚构resource通过。

root 应先合批全部方向修复，prepare后确认真实新 GN target flags与最终libace_compatible
solink flags，再构建一个ARM64 phone新代表包。使用同commit的新 package/profile/inventory
走 observe、whole TU compile、最终DSO完整源码/链接/CFI/镜像bytes、实际loaded role、UI
session、普通定位API真实轨迹/围栏/行政区/BLE/权限/取消/off/重启回归。电话12个已路由
接口还需真实 modem/SIM/IMS/RTT peer、payload/session、off静默和退出，广义radio finding
也仍需要真实实证。工具修复和host通过没有关闭这22项中的任何一项。

新代表包完成完整281项/47项同boot验收后，再按ABI与device profile验证其余五包；
本批没有构建任何镜像，也没有放行六包矩阵。
