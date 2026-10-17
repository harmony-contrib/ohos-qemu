# OpenVPN product publication handoff

2026-10-17。仅修改授权的 `scripts/build_product_openvpn.py`、`ci/capability-audit/test_openvpn_product_output.py`，以及本报告目录。root 已审查实现方向，本批交付后释放两文件写租约，不再修改。

## 根因与修复

root 报告代表构建 `r53-first-arm64-phone-full-build-02` 在 publish 阶段失败：真实 `source-build` 是 GN 预先建立的 0755 空目录，没有 receipt 或任何内部路径。旧实现把所有既存目录都当作必须有完整 receipt 的旧产物，因此拒绝。实际完整 attempt artifact 已由 root 保留；agent 未读取或改动实际 source/out。

现在完整校验新产物及证据后，对真实空目录直接 `os.replace(source, destination)`。不先删除、不移动空目录到备份。若检查和 rename 之间出现未知文件，真实目录 rename 由内核拒绝；若出现 alias，同样不能用目录 rename 跟随或替换该 alias。失败向上传播，保留新 attempt 和 caller 内容。父目录中的 GN stamp/NOTICE 不受影响；目标目录内存在 stamp/NOTICE 仍属于非空未知内容，不能据名称绕过检查。

非空旧产物继续采用受控验证后整体备份的规则，并补齐自身证据检查：

- receipt 必须是非 alias 的实际文件且 JSON 为正确组件/schema/product/status/runtime 状态的 object；binary 必须是非 alias 的实际文件且 SHA256 匹配。
- commands 必须是非空 list，元素为 object；log 必须是安全单层 basename，exit_code 必须是整数 0，实际非 alias 日志及 SHA256 必须匹配。空/缺失/畸形/修改后的旧日志不移动任何内容。
- 历史 recipe 必须有非空安全相对文件路径→SHA256 映射；每个 SHA256 格式合法，并按现有 sorted JSON 算法复算 recipe_sha256。允许合法历史 recipe 与当前源码哈希不同；新产物 recipe 仍必须等于当前 recipe。
- 验证通过的旧目录，包括附带 caller 文件，整体保存在随机 `.previous-*` 目录。若第二次发布 rename 失败，旧备份和新 attempt 均保留；该既有两步流程不承诺目标路径持续存在。

## 先失败后通过

先添加全部 16 个测试方法及参数化反例，在**旧实现**执行同一命令，exit 1，22 个失败与 8 个错误，见 `before-fix.txt`；旧脚本和测试 SHA256、准确命令、exit_code 见 `before-fix-receipt.json`。失败覆盖真实空目录拒绝、旧日志和 recipe 未校验、alias receipt 及畸形输入。

修复后相同 16 个方法全部通过，见 `after-fix.txt`。测试使用真实临时文件、目录、symlink 和内核 rename；竞态测试只在 os.replace 边界插入未知文件或 alias，然后调用原生 os.replace 确认拒绝。另注入 EACCES 验证空目标发布失败保留双方，以及受控旧产物已备份后的第二次 rename 失败仍保留旧证据和新 attempt。

从仓库根目录执行：

```sh
python3 -m unittest discover -s ci/capability-audit -p test_openvpn_product_output.py -v
```

环境为 macOS arm64 / Python 3.13.7；没有 native 编译、Docker、SDK、VM、构建包或 Git 提交。`git diff --check` 通过。最终源码/test SHA256 和详细边界在 `result.json`。

## 集成与未验证范围

root 负责重跑整个 `test_openvpn_*` 受影响集合，并在独立 Linux 容器补验，然后集中提交本轮已知修复。agent 的测试 fixture 明确标记为 unit payload，并非完整 native build、package 或 guest runtime 证据。

实际 GN action/native build、下一代表归档创建、完整新包行为验收仍未通过；首包完整 gate 通过前不能扩展到其余五包。历史 recipe 自身 hash 一致性不等同于对不可用历史源码的独立认证。此次空目录发布竞态由内核类型/非空检查保护；既有非空受控目录在校验与备份 rename 之间的并发修改仍沿用整体备份保留机制，没有新增原子身份认证事务或压力测试声明。
