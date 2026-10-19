# 最终整合独立静态验收

未发现静态整合阻断。审查HEAD为`721798e1159da9b213c3f92d5a3c17207e505fe6`，其tree与内容提交`574487d90063e71e0342459c419cba5e64aa9c02`相同。

- 独立读取实际Git parent链：tracked清单29个原tip全部是HEAD祖先；不是照抄清单中的ancestor_of_base。实际读取676个commit元数据，逐tip距离见result.json。
- 相对a0d没有删除任何文件。已有路径仅AGENTS、协调计划和packager变化；当前builder、Calendar runtime capture/main_ui guard及原同名Calendar测试保持a0d原字节。
- 六组原候选共119个文件项：116项原字节相同。另3项是selector中立cwd修复及新增回归、peer packager增量。旧Calendar CRUD测试原字节保存在新名test_batch_system_calendar_crud_candidate.py，未覆盖当前main测试。
- packager严格116行新增、0删除；原a0d全部行仍按序保留。UTC RTC、完整find型SHA256SUMS和PrivacyCenter来源/镜像校验块都在，精确行号见result.json。
- 当前只有本地分支codex/ohos7-integrated-development，指向审查HEAD；14个旧linked worktree的HEAD均为裸SHA，全部detached。它们仍作为历史目录保留，并未物理删除。
- 观察到的未提交修改仅docs协调计划。没有运行tests、SDK、编译、crypto、容器、VM/HDC或任何资源，没有改开发树或Git。

此结论是候选保全、历史归属和静态内容验收；不宣称这些候选已接当前build/source或通过新包行为验收。每组尚有的真实接线、权限/身份和runtime依赖继续有效。
