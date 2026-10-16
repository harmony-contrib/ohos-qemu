# GNSS：真实 OHOS ARM64 ABI / CFI 消费端验证

本批在 QEMU-user 中实际运行 OHOS ARM64 消费者，复验返回 **0**。
源码、编译器、生成 public headers、vendor ABI 和整个依赖闭包均为真实现有文件。
依赖闭包含两份 CFI/LTO 产品 DSO 在内共13个 ARM64 模块，没有替代接口或运行时。
本批不改产品代码，不启动产品构建或打包，不核销任何需求。

消费端真实使用 `GnssInterfaceImpl`，经生成的 `IGnssInterface` public
配置/normal Start/Stop 虚调用进入 HDI DSO，再由实际 loader 的函数表进入
`vendorGnssAdapter.so`，最后经真实 proxy callback 返回消费端。
额外 `dlsym` 验证的是 `GnssVendorInterface` 数据对象及其 getter，
没有把数据符号伪装成函数。实际尺寸为 device16 / table96 / location88 /
public config16 字节。

复验观察到：

- 无输入期间没有位置回调；只有发送外部协议测试向量后才有两次精确匹配的回调。
- 第一回调重入 `DestroyInstance` 返回；provider 回调返回后，外部 reaper
  完成清理并实际卸载。此后同进程重新加载，第二代没有沿用旧回调或位置。
- 第二代收到旧 nonce frame 后断开。重连取得新 nonce，发送新 frame 后才有第二次回调。
- public Stop 后短暂观察无新回调，重复清理完成；两次 provider 映射各有一次
  `munmap(...,45056)`，最终私有 input socket 消失。
- 消费者及原产品 DSO 保留 cross-DSO CFI、LTO、产品 blocklist/trap 选项。
  消费者定义 `__cfi_check`，反汇编有 12 个 `__cfi_slowpath` 调用点。
  本批未执行故意错误类型的 CFI 拒绝测试。

首次运行返回1：新消费者把 Config 放在 Enable 前，真实 provider 因 input
尚未启动拒绝 SetBatch。修正测试的调用顺序，同时集中修正 STREAM 传输、
完整 hello 读取和旧 nonce 拒绝后的重连，再复验通过。首次完整日志及测试源码
原始哈希均保留；产品源码和两份 DSO 未变。

真实 QEMU-user 运行环境还报告 `/dev/__parameters__/param_sec_dac` 缺失及
HiLog server 连接失败。复验日志分别保留12次参数路径访问及55次日志连接报错；
本批调用路径没有因此中断，没有伪造参数共享区、日志服务或 Binder。

复验消费者 SHA256：
`a0c08e06103cab0a46e1a3647e49ad2a7a2685cd0751978fb8c35fbaeb81ed28`。
原 provider SHA256：
`ccdded90a93f95f27928f3d3a8fd8834da689ee2e68d4f32566bab0beebfce4e`。
原 bridge SHA256：
`c8f7a26c745039983ad366633861f7b690b1222cacb9fb425a3c12685aede6c0`。

全部命令、编译/链接选项、真实 header 哈希、运行库来源、ELF、输入字节与 nonce、
退出码及原始日志见 `attempt01-*` / `attempt02-*`；独立核对见
`independent-checks.json`。原 R52 产品链接证明保存在 `r52-real-product-links.json`。
原始 readelf 文本含工具生成的行尾空格，仓库中使用 `.gz.b64` 无损保存；
解码后的 SHA256 记录在 `result.json`，私有目录仍保留完整原文。
完整二进制、运行库副本及两版消费者源码保存在：

```
/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/system-gnss-ohos-abi-r6-20261016-01
```

`private-artifacts.json` 给出这些文件的哈希。初版测试文本通过逆向本批测试修改
恢复后，与执行前独立记录的两个 SHA256 精确一致；相关记录在
`candidate01-source-recovery.json`。原失败日志和原始 freeze 未改动。

唯一租约容器 `ohos-system-gnss-ohos-abi-r6-20261016-01` 为2核/5GiB，
共享 source/out 和 R52 artifacts 只读，私有 `/tmp` 可执行，无网络。
峰值内存340975616B，容器于 `2026-10-16T13:52:11.966038+00:00`
移除并归还租约。只有容器内部创建了1022:1022、0700专用目录；
消费者和外部 peer 在容器中以 root 运行，没有修改宿主或产品权限。

本证据不等于启动新 OHOS 客体：QEMU-user 仍使用 Linux 宿主内核。
本消费者未走 public EnableGnss 的 `hdi_objcast`/IPC callback、HDF服务发现、
Locator/普通HAP/融合围栏、location_host 实际身份或 SELinux 权限边界。
协议向量是明确标识的测试输入，不是真实地理测量或精度证据。
这些路径以及新代表包完整门禁仍由主 agent 验收；原10项 system 需求仍各保留一次
review 和 remaining gap，关闭数0。
