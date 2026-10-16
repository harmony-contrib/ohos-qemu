# ARM64 phone 首次完整新包：执行入口与接线检查

本轮只读检查主树从 `afa564ae0f4a603d933f63e9cff78674ed8e3cbf` 到
`f2ddb5142274fd5328587a66c200bc300a0cf905`；后者新增的签名/预装选择修复已单列在主树，本文不重复评审其实际签名结果。
检查现有只读 inspector 的 `/ohos`、混合 `/ohos/out` 和已保存的 R50/R51/R52 证据。
没有运行 GN、Ninja、SDK、QEMU、HDC、产品构建或镜像操作，没有修改上游源、共享脚本、权限或其他 agent 路径。

**整包执行入口已经存在；当前不能把旧 out 或两份独立 GNSS DSO 当作可交付新包。**
首包冻结前还需合批 Contacts/Theme 的真实整包选择/业务接线，以及下列能力的正式运行探针和闭合验证。
GNSS/sensor 的主树构建与静态镜像检查接线已有实现，尚未应用到此次只读源/图；必须通过新的完整 source plan、load、GN 与 images 构建生成，而非搬旧 staging。
这份清单区分“代码尚未接入”“图待重新生成”“已有候选证据但仍待新包运行”，不把三者统称编译失败。

## 首次冻结前集中处理

| 检查 | 已确认的当前状态与精确位置 | root 的必要动作与验收输出 |
| --- | --- | --- |
| GNSS 新 provider 与完整三 DSO | `scripts/build_standard_qemu_in_docker.sh:3070` 已调用 provider installer，`:3072` 调用 `prepare_qemu_gnss_runtime.py`；runtime group 依赖 `//device/qemu/common/virt_full/external_gnss:qemu_external_gnss`。`verify_qemu_gnss_image.py:LIBRARIES/GRAPHS` 明确要求 provider、HDI bridge、业务 `liblbsservice_gnss.z.so` 三者。只读源中两个新 BUILD.gn/对应 ninja 均不存在；旧业务 ninja 存在。 | 合入 location 业务修复与桥/provider 后走完整图，实际生成第三业务 DSO，保留 `gnss_ability.o`、`gnss_event_callback.o` 新输入与链接证明。R52 的实际 CFI 链接只含 provider/bridge 两 DSO。不得将它当第三 DSO 新产物。 |
| GNSS 安装/权限 | `prepare_qemu_gnss_runtime.py` 已提供专用 init/para/group/policy；常量 standalone=1。provider 输出严格为 `vendorGnssAdapter.so`。只读 phone staging 缺该文件；旧 bridge 与业务 DSO hash 见 inventory。 | 新图安装 vendor provider/bridge、system 业务 DSO。init 建 `/dev/unix/socket/qemu_gnss` 0700 location_host1022；provider socket0600。保留精确 SELinux 与受控 root controller 权限。实际设备确认 driver/loader mappings、UID/domain、fresh nonce 输入到公共定位/融合围栏，stop/restart 与普通应用拒绝。 |
| Sensor/MSDP 图和选项 | builder `:3340–3346` 已 apply VDI/MSDP 并 prepare runtime；phone profile `:247–252` 与 `patches/lib/sensor_features.py` 要求 community=true、qemu_external=true、sensor_enable=true、allow_mock_fallback=false。只读 preloader 四项皆缺；旧 sensor ninja 只有 `sensor_impl.o`，无两个 qemu 对象。 | 完整 source plan→load 校验四个**布尔**值→重新 GN；链接安装新的 vendor `libhdi_sensor_impl.z.so`，保留 qemu_sensor_input.o/qemu_sensor_vdi.o、hdfVdiDesc、实际数据标签及匹配镜像 inode/hash。现有 R52 full TU/实际 VDI link/mini-ext4 检查不是整包 HDF 使用证明。 |
| Sensor 实际加载与安全输入 | V3 SensorService 首选 `libhdi_product_sensor_impl.z.so`，再 fallback `libhdi_sensor_impl.z.so`；当前旧 staging 前者不存在，但新包仍须复核无 shadow。`prepare_qemu_sensor_runtime.py` 已提供专用目录/policy。 | 新包确认 sensor_host3033、GIDs3033/3066、domain、0700目录 `/dev/unix/socket/qemu_sensor`、0600 `/input`，实际 fallback DSO被加载；以新挑战三轴 m/s² 经 VDI→HDI→SensorAgent→MSDP 实算法验证。无输入不产生事件，错误nonce/seq/peer、断开、disable/unregister/重入/重启拒旧代；不允许启用 MockHandle 假通过。 |
| Contacts 源选择尚未接 shared GN | 候选 `patches/common/applications/standard/contacts/source_provider/0001-build-fixed-real-provider-sources.patch` 新增 `//applications/standard/contacts:contacts_hap`。主 builder 没有此 installer 调用；实际只读源该 BUILD.gn 不存在。`applications/standard/hap/BUILD.gn:228–233,401,462` 仍是 prebuilt Contacts 及其两个 group 引用。 | root 统一接 installer 与 shared HAP group 选择，消除同名输出双来源；真实 SDK26、OS profile/HAP签名、预装/BMS策略/镜像 guard，保留38权限、7HAR及真正 `com.ohos.security.pickersheet/pickersheetlibrary` HSP。不能删 HSP 依赖来完成编译。普通 contact picker/session与权限生命周期必须设备验证。 |
| Theme 源选择及真正 wallpaper UI/provider | 候选 Theme patch 新增 `wallpaper_phone_hap` / `wallpaper_pad_hap`，都输出 Wallpaper.hap；builder/shared GN 没有消费者，只读源 BUILD.gn 不存在。固定模块为 `WallpaperExtAbility` renderer feature；原 OS profile 已过期。真实 native `base/theme/wallpaper_mgr/services/src/wallpaper_service.cpp` 在无 ThemeService 时仍回落 launcher/WallpaperExtAbility。 | phone只选 phone target，2in1只选对应 pad target；真实更新受限 ACL 的合法签名与预装/BMS/镜像检查。另接真实选择/设置/恢复/取消 UI 与 native 目标路由。现有 renderer feature 自身不是 wallpaper 设置 UI，单纯签好 HAP 不能核销缺口。具体源码/签名约束见 apps 的 `contacts-theme-source-preparation.md`。 |
| 正式探针和 closure 未接入 | 当前 `ci/capability-audit/run_packaged_qemu_suite.py` 与 `verify_gap_closure.py:behavior_results` 无 challenge GNSS/Sensor 或 Contacts/Wallpaper provider UI 的注册调用/闭合器；后者`:706,717` 的已有 Contacts collection/export 检查明确排除 backend/picker/permission behavior。具体 ID/关键字零命中见 entrypoints JSON。 | root 在冻结前把真实普通 API/权限/UI/受控输入探针、独立证据验证器及具体账本 ID 接入完整 suite。每条闭合绑定新 archive SHA、同一 acceptance boot、nonce及源哈希。既有 host harness/QEMU-user consumer/传输send成功不能作为公共API闭合。当前正式 closure 要求所有 expected ID，缺注册不能得到完整通过。 |
| 其他真实服务依赖 | 本组10项仍未核销；OEM DeviceAttest合法身份/key/服务、真正 ads provider、SecurityGuard有效风险模型的依赖未由本轮只读工作补齐。其他组需求也不由这份清单宣告通过。 | 若目标是用户要求的全部修复后首包，必须先解决这些真实依赖和各组未完源码，不能靠返回空值成功/假凭据/新增排除补账。诊断包可以编译，但不能称交付门槛已就绪。 |
| Mesa/RenderService 与 HiTrace | 当前 private LLVM Mesa/GN action/image-byte guard 已接主 builder；独立新 consumer PASS。R50/R51 原始失败仍无同包同序列新验收。 | 使用当前 recipe 的六个 Mesa库与证明，保留正常 watchdog、无外部keepalive的boot/suspend/wake检查，再跑普通 HiTrace 完整前序负载。确认 RS PID稳定与真实 kernel records，不用独立 surfaceless/QEMU-user 短测替代。 |

上述还不是整个82缺口的新审计。本轮只对请求中的构建入口、GNSS/Sensor、Contacts/Theme和R50/R51做定点复核；权威未核销基线不变。

## 现有执行路径和最小命令

以下是**交给 root 后在唯一 heavy lease 下执行的命令模板**，本轮没有执行。
所有已知源码、签名和正式 probe/closure 接线应先集中完成。构建 wrapper 每次会自动冻结 `scripts/patches/ci` 等输入，输出 `build-inputs.json` 与 tree SHA；不要在第一次新包打完后才修改验收逻辑。

1. 检查源码/候选输入的 host guards；可选 `PREPARE_ONLY=1` 走完整 patch plan，仅作 source preflight。
   `SOURCE_PREPARE_ONLY=1` 在能力 patch plan 前返回，不是上述预检的替代；`BUILD_ONLY_LOAD=1` 仅跑 preloader/feature校验，不保证生成新 ninja或链接。`PATCH_COMPONENTS_ONLY=1` 是内层 builder 的现有模式，外层不直接转发；本文不建议绕过正式 wrapper。
2. 仅 ARM64 phone 构建并打包一次：

```sh
# 接线合批后；选用已验证的 native source/out 卷与当前缓存。
LC_ALL=C LC_CTYPE=C LANG=C \
DEVICE_TYPE=phone PRODUCTS=arm64_virt \
DOCKER_IMAGE=ohos-qemu-build-env:7.0-release-gn-qemu-user \
BUILD_JOBS=2 KERNEL_BUILD_JOBS=2 \
BUILD_ONLY_LOAD=0 PREPARE_ONLY=0 SOURCE_PREPARE_ONLY=0 \
OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE=0 \
bash scripts/run_2in1_full_build_docker.sh
```

   wrapper 默认 DEVICE_TYPE=2in1、PRODUCTS含三架构，因此两个显式选择不可省。源码默认来源是 native Docker volume，并非较旧的宿主 `/Volumes/PSSD/qemu/openharmony`。不要把只读 inspector 的混合out当 freshgraph。
   现有缓存如已完整且固定来源校验通过，可按 root 既有方式显式设置 `SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 SKIP_GIT_LFS=1 SKIP_APT=1`；这些值不是跳过源锁/签名/镜像门禁的授权。各 M144/LLVM/ArkWeb等依赖 wrapper 原有检查照常执行。

   内层 `build_product()`（`:1504`）先 load，再 `build.sh --product-name arm64_virt --build-target images --build-only-load=false --device-type phone`；继续 `package_product()`（`:1635`）调用 package_standard_qemu.sh。无需人为新增“仅拷三个SO”打包途径。
   full phone packager 已绑定 Mesa六库、OpenVPN、sensor/runtime、GNSS三库、ArkWeb、sharedfence、Photos/Settings/Admin/MMS、字体与bootassets各检查。它们是离线构建/图/字节证明，不是首包运行通过。
3. 从该次 wrapper 日志记录冻结目录为 `FROZEN_INPUTS`；从真实输出记录新的唯一 `NEW_ARCHIVE`、`EVIDENCE_OUTPUT`。使用实际宿主 API26 SDK/HDC、现有兼容 Python 环境与 bindings checkout；不得指向R50/R51旧包。

```sh
LC_ALL=C LC_CTYPE=C LANG=C \
QEMU_TEST_SDK_HOME="$ACTUAL_API26_SDK" HDC="$ACTUAL_HDC" \
QEMU_TEST_PYTHON_ENV="$ACTUAL_RUNTIME_VENV" \
OHOS_NATIVE_BINDINGS=/Volumes/PSSD/code/ohos-rs/ohos-native-bindings \
bash "$FROZEN_INPUTS/scripts/validate_packaged_qemu.sh" \
  --package-archive "$NEW_ARCHIVE" --evidence-output "$EVIDENCE_OUTPUT"
```

   `run_with_owned_hdc.py` 管理自己的 HDC/端口/临时目录；suite 在同一个新 acceptance guest 中先无外部keepalive启动、60秒稳定、实际suspend/wake/PID检查，随后应用/系统能力检查，包括普通 HiTrace。较长屏幕 override是之后的有限应用阶段，不能跳过前面的电源门禁。
4. 最后独立复验同一归档与该次总 evidence；suite也调用同一 verifier：

```sh
python3 "$FROZEN_INPUTS/scripts/verify_first_artifact_gate.py" \
  --archive "$NEW_ARCHIVE" --evidence "$EVIDENCE_OUTPUT" \
  --repository "$FROZEN_INPUTS" --product arm64_virt --device-type phone
```

   保存归档路径/SHA256、实际输入 manifest/tree、guest/host环境、命令、boot ID、失败与结果。若失败，把同轮全部可收集失败合批修复后，再重新冻结/构建/验证代表包；只有此完整门禁 PASS 才能进行其余五包。

## R50/R51：失败边界及候选覆盖

- **R50** 归档SHA `879933a2fca5e8bdf6fb21705e95f97ce7ed1e95f85bb038cf86f6ec30a73370`，完整失败 boot `17fcc26b-ed41-41e8-a2ec-726b095cf0ba`。39项先前检查通过后，普通 HiTrace 当前nonce结果未在90秒内完成。原始 `aa start` 实际 exit0、日志为 `start ability successfully.`，所以应精确叫“启动后调用方完成超时”，不是已证明 aa CLI启动失败。实际 raw hilog/提取栈中有 `WindowScene::GoBackground → NotifyAfterBackground → SetMainFrameRateLinkerEnable → SyncFrameRateRange → synchronous Binder SendRequest` 阻塞；该旧 app PID与最后普通HiTrace PID的精确归属、RS延迟原因仍未证明。
- R50后仅新增失败快照；另一个boot `d0a0da9f-c8f2-4b9e-a617-6fcd1d6ea627` 的短诊断有36 kernel records、2 native generations和越32位counter，证明那条短路径可运行。它没有重演原完整负载/同boot，不覆盖原失败。当前 runner仍保留90秒完成要求和失败采集，没有修复证据能把原项改为PASS。
- **R51** 归档SHA `6b27a2062a8b4361255d26499d1fcf86685d0f0f4d686dfd3965acdede28fbfe`，boot `a1f293cc-5726-4630-8965-2b31b25407e7`。未开始后续能力检查即失败：无输入稳定观察及实际s2idle/单次wake之间，RenderService PID665→2574，init记录旧进程exit0；内核boot ID没换。suspend entry61.862124s、render exit91.718662s，exit0不构成原因解释。
- 原 `SERVICE_BLOCK-665-20261015074146.log` 已与该包Build-ID符号绑定：main等 `RSDrawFrame::PostAndWait`，RSUniRender在 `tgsi_exec_machine_run`/vector arithmetic/index register/softpipe fragment execution/Skia glDrawArrays。堵塞已发生在休眠前。旧Mesa已-O2且LLVM disabled，不能把加-O2或shader编译当已证实根因。
- 当前 Mesa backend实际启用llvmpipe、保留softpipe、静态private LLVM10，六库新recipe/图/镜像一致性检查已接；`r51-mesa-integrated-consumer-05` 编译与独立渲染证据是候选支持。它直接改变原softpipe热点所处渲染后端，但没有证明新的实际RenderService在完整boot/sleep/wake/HiTrace负载下不阻塞、不重启。保留正常watchdog与相同完整门禁，不能由短诊断核销。

`historical-failures.json` 记录14份实际文件的hash、原始路径/错误、成功aa命令与其hash；归档hash引用原始controller记录，本轮没有重新读两个大归档。
`readonly-source-out.json` 保存23个精确源/图/安装路径及四feature实际值；`root-entrypoints-and-guards.json` 保存23份主树文件hash和行号；`prior-candidate-evidence.json` 保存已有候选证据实际hash/范围。
