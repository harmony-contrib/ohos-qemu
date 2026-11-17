# Binder 对象读取与 FD 清理

固定到 OpenHarmony 7.0 Release IPC 提交 `b8d3e96cfcf382c8fae54502679ac8b3d827b428`。

保留 Binder 对象合法的四字节对齐，不把 Binder64 自然对齐要求写入协议。
读取对象时复制到对齐的局部结构，保持现有 token、对象注册和 cookie 校验。
Parcel 清理使用减法检查对象边界，并正确释放合法 FD 0。

接管前拒绝/分配失败共用无堆分配的普通 FD 关闭检查，然后通过既有
`FreeBuffer` 释放真实内核事务。只主动关闭内核送达的 `BINDER_TYPE_FD`：
FDA 数组仍由内核在释放缓冲区时关闭，FDR 不属于 Linux Binder 送达对象。
`ReadAshmem` 的 nothrow 分配失败关闭本次 duplicate。rawData 远端状态改用
负值哨兵，与合法 FD 0 区分，保持对象布局、公开 API 和驱动权限不变。

由统一构建脚本在部件遍历前应用。三个 ABI 的真实编译及新镜像 IPC/应用
回归通过之前，不代表第一产物验证门禁通过。
