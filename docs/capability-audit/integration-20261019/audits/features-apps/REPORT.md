# 旧feature分支整合复核

**本次指定的9个提交没有发现需补回的独有代码。四组旧分支均已通过GitHub squash进入a0d历史，四个旧分支末端与对应squash的整树OID完全相同。应保留当前新版脚本，不应再次整批cherry-pick或恢复旧overlay。**

审查基底：`a0d62155747253f203952878594e21976c12a92c`。只执行只读`git show`/`git diff`和标准库文本/哈希比对；未执行候选、tests或任何资源，未写开发树或Git。

|旧分支/提交|a0d可达的squash|整树OID（旧tip=对应squash）|结论|
|---|---|---|---|
|feat/qemu-a11y：`6ddac55`, `98932bb`|`837a853974cd0c3051bf1f4278e860575949dbb7`|`42acac93ff44332ee2ddf68a12b8e1e5a719ac27`|已整合；后续保留或更新替代|
|feat/qemu-device-type-matrix：`efdf5c2`, `29cbcd3`|`b77b343de26085986633f94f360b7445b6cd56c7`|`dbf5eef765cd369e6802e63066c76cca1ee230a3`|已整合；后续保留或更新替代|
|fix/2in1-window-manager：`c1d3c97`, `12344a`, `bf938de`|`5fdf3b3e82fcfa9b00e1a555ee7de4d9d2fd93da`|`f53d62a2af8bb45676c0a17f642d600ab5a7c80e`|已整合；后续保留或更新替代|
|fix/standard-qemu-gpu-matrix：`2685329`, `4ce1135`|`57efeeb612f3b66886b7224f4705bb51ced7c251`|`ee9c03f760ac1f9f3b47d5a9a738c549c1c21239`|已整合；后续保留或更新替代|

可达性由`git show a0d^{/PR主题}`解析到精确squash提交证明，不依赖同名分支或仅看subject猜测；每组还实际比较旧tip与squash全树`git diff --name-status`为空。window-manager组的中间merge也保留parents关系。完整命令与对象pins均已保存。

## 逐commit结论

|提交|原字节保留文件数|同路径更新替代|旧路径迁移/重构|需恢复独有代码|
|---|---:|---:|---:|---:|
|`6ddac55c0f7c9bae8a5fa6293363da51279002be` feat: add OpenHarmony 7.0 QEMU compatibility components|21|11|0|0|
|`98932bb214b92eee1332ef7ba2b455f19233b2d1` build: pin and verify six OpenHarmony 7.0 QEMU images|4|8|0|0|
|`efdf5c28f1a8d8a848e043d07de0447761dc37a1` feat: add full phone and 2in1 QEMU profiles|2|4|7|0|
|`29cbcd39d02b4c86742e41677d971bca89818767` feat: build six-package device type matrix|0|3|0|0|
|`c1d3c97cfd4cc8c471b4515a868896f762051d5f` fix: validate native child processes across six QEMU profiles|21|9|0|0|
|`12344a08a695e10123825f48560fb6a5c11c442f` fix: enable SceneBoard window manager on 2in1 QEMU|10|9|1|0|
|`bf938def98c787bd1a99c01cff48d236571c9c2f` fix(ci): use portable dd block sizes|0|1|0|0|
|`268532998a1719b66203351e897df57c54a2ca5a` feat: bundle HAP signing tools with QEMU packages|4|2|0|0|
|`4ce11356999792a36661678f18df165706537b3f` fix: restore portable standard QEMU GPU rendering|4|7|5|0|

## 容易被误认成遗漏的路径

- `overlays/qemu_{phone,2in1}_full/*`已迁至`patches/{phone,2in1}/product_profile/`，两个apply.sh原字节相同；当前profile附加合同、SceneBoard与后端选项，不能恢复旧monolith。
- `overlays/armv7a_virt_full/apply.py`已拆到`patches/common/device/qemu/armv7a_product/`有序组件。旧`build_armv7a_mesa.py`的81行原字节完整嵌入`components/device_qemu/0001-add-armv7a-qemu-device.patch`新增文件payload；SHA相同。旧入口/marker不保留是当前README明确的迁移契约。
- `overlays/standard_qemu_vpn/*`已拆到`patches/common/standard_vpn/components/`。64位`build_qemu_mesa.py`与旧文件原字节相同。qemu_mesa/graphic_2d_egl/内核/code_sign/xpm/vpn_dialog等仍由有序入口接线；旧Vulkan禁用baseline被后续用户要求的实际Vulkan能力更新替代，不应还原旧禁用。
- `scripts/configure_2in1_runtime.py`已更名`configure_sceneboard_runtime.py`；完整内容只有docstring和print文字变化，实际参数更新、metadata/SELinux保留与读回逻辑相同，并扩用于phone。
- `patches/2in1/sceneboard_runtime/apply.py`改为shared`sceneboard_assets.main(2in1)`薄wrapper；四个精确module、ABI库检查、签名/profile和CEM用户路由逻辑仍在共享库。原两个unlock/CEM patch与release/VM验证工具原字节保留。
- `bf938de`的六处`dd bs=1M`全在当前`ci/device-type/test.sh`保留；没有恢复Mac易出问题的`1m`。
- arbitrary accessibility ability CLI原patch、七个ALSA patch、旧native-child两patch、签名安装脚本及多个验证/说明文件仍原字节一致；apply/CI/包脚本在此基础上添加enum、config/callback、profile/来源和行为门槛。
- 当前矩阵仍为phone/2in1×三架构，新增首个代表包真实行为gate之后再跑余包。这个严格门槛是应保留的后续更新，不能由旧未设gate的matrix覆盖。

## 文件级证据

`FILE_RECONCILIATION.json`包含全部133个commit×file行（103个唯一旧路径），每行给旧/当前blob SHA、分类、迁移目标和理由。`CURRENT_SOURCE_EVIDENCE.json`给真实Mesa payload字节相等、两个wrapper迁移、参数脚本差异、六个dd及当前关键接线行号。`FOCUSED_DIFFS.diff`保留所述更新的必要文本差异。没有生成待应用代码patch。

当前新版脚本的存在和上述整合证据不等于新包运行通过，也不降低原代表包/完整账本门槛。结论仅用于清理旧本地分支前的代码保全判断；本次未执行分支/worktree清理。所有报告一次性完整冻结，冻结后不追加。
