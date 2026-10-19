# 旧 worktree 清理前保全清单（元数据盘点）

主树 `/Volumes/PSSD/code/ohos-rs/ohos-qemu` 已排除。其余 **14 棵 worktree** 的两组 Git 列表均 exit0。盘点前后 worktree 清单相同，未做删除、归档、打包或 Git/工作树修改。

共 **2533 个 regular 文件，52,104,078 字节（49.69 MiB）**。按 inode 去重后相同，没有重复 inode。st_blocks×512 合计 57,569,280 字节。另有 114 个被 Git 压缩成目录条目后递归展开的目录；不把目录本身 st_size 算作文件内容。

- Untracked：Git 原始 60 条；不跟随链接展开目录后 653 个 regular 文件，7,577,981 字节。
- Ignored：1880 个 regular 文件，44,526,097 字节。
- 符号链接 0，外部 source/out 链接 0，其他设备/FIFO/socket 条目 0。
- 没有 ≥100 MiB 文件。最大文件 2,707,178 字节；没有巨型编译产物或镜像。
- 路径/枚举/lstat/readlink 错误 0，untracked 与 ignored 原始 Git 列表无重叠。

| Worktree 目录名 | Untracked 文件/字节 | Ignored 文件/字节 | 合计字节 |
| --- | ---: | ---: | ---: |
| audio-incarnation-validation | 0 / 0 | 0 / 0 | 0 |
| calendar-runtime-validation | 0 / 0 | 0 / 0 | 0 |
| capability-batched-repair-e | 0 / 0 | 100 / 2,606,063 | 2,606,063 |
| capability-batched-repair-f | 0 / 0 | 12 / 132,483 | 132,483 |
| capability-core-next | 0 / 0 | 0 / 0 | 0 |
| capability-qa-validation | 0 / 0 | 2 / 11,755 | 11,755 |
| capability-runtime-qa-batch | 0 / 0 | 182 / 3,880,503 | 3,880,503 |
| capability-runtime-qa-repair | 0 / 0 | 201 / 4,373,966 | 4,373,966 |
| gnss-precision-validation | 0 / 0 | 0 / 0 | 0 |
| ohos-capability-apps | 0 / 0 | 47 / 575,051 | 575,051 |
| ohos-capability-location | 0 / 0 | 1150 / 29,986,600 | 29,986,600 |
| ohos-capability-media | 0 / 0 | 99 / 1,751,731 | 1,751,731 |
| ohos-capability-network | 645 / 7,572,695 | 34 / 485,396 | 8,058,091 |
| ohos-capability-system | 8 / 5,286 | 53 / 722,549 | 727,835 |

建议 root 在清理前保留整套清单中的内容，总量不足 50 MiB，无需为了节省备份量删选历史来源。Network 的 `.network-scratch` 包含未跟踪源码/fixture/编辑脚本与嵌套源码目录；System 有 8 个未跟踪的 Calendar NAPI native lifetime stub header；Location 的 ignored `.tmp/location-round*` 占比最大，含旧源导出与 JSON 记录。其余 ignored 文件包含主机缓存和历史私有材料；是否弃用属于 root 后续判断，本盘点不删任何内容。

文件级完整记录在 `FILES.jsonl`：每行保留 worktree、Git 类别、相对/绝对路径、类型、mode、size、st_blocks 字节、mtime_ns、dev/ino/nlink、目录展开来源。`SUMMARY.json` 保留逐树实际 argv/退出码/Git NUL 原始列表 SHA、分类统计、完整限制。`raw-git-lists/` 保存两组原始 NUL 列表及 stderr，`TOP_FILES.json` 保存最大的 25 个文件。

实际列举命令为每棵树的：

```text
git --no-optional-locks -C WORKTREE ls-files --others --exclude-standard -z
git --no-optional-locks -C WORKTREE ls-files --others --ignored --exclude-standard -z
```

目录展开只针对 Git 输出的目录条目，逐层 lstat + os.scandir；符号链接本身只记录 raw readlink 与 lexical 目标，不 resolve、不 stat 目标、不递归跟随。虽然本次没有链接，root 备份时仍应禁止 dereference。

这是一次元数据快照，没有读取或哈希被列举的源文件内容，没有证明后续内容不会变化。逻辑大小不是压缩归档大小，st_blocks 也不等于 APFS clone/snapshot 的独有物理占用。root 应在串行备份时保留字节/metadata，并以实际备份回读检查后再清理；本清单不是已备份凭证。Tracked 文件、Git 历史与分支清理不属于本清单范围。

输出目录冻结后停止写入。未运行候选、tests、SDK/编译、crypto、Docker、VM、HDC、QMP；没有删除或打包。
