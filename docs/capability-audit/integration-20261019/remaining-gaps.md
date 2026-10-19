# 合并后还有哪些工作（2026-10-19）

已统一 29 个旧分支的历史，补回 6 组独有候选，保留较新生效实现。
现在只有 `codex/ohos7-integrated-development` 一个本地分支。

当前能确认的完整实现交付缺口至少包括 6 个应用领域 finding：读屏、实时字幕、
桌面歌词、扩展文本菜单、文本服务三插件聚合、号码身份/标记数据服务聚合。
**这只是明确下界，不是全项目只剩 6 项。** 还存在下面列出的部分实现、协议、
构建/预装接线及实际外部输入缺口。现有证据不足以给出可靠的“纯缺实现”精确总数。

历史未销项需求共 82 个，已全部逐 ID 核对到当前源码评估，见
[remaining-requirements.json](remaining-requirements.json)。82 不能当作当前缺实现数；
主机通过也不能自动关闭原需求。下表各数字均为该历史集合内的原 ID，互不重复。

| 能力方向 | 当前源码评估 | 下一批工作 |
| --- | --- | --- |
| 应用 / 入口 / 无障碍（34） | 11有主要修复待完整验证；13部分实现/接线；6尚无完整交付；4需重判 | 完整provider/插件实现；Settings select与当前Share依赖/guard/build参数组合；MMS附件授权、AVCast/音量、策略/APN/通知/相机/隐私入口协议。Contacts、Wallpaper等已有修复需新包边界回归。 |
| 网络 / 外设 / VPN（9） | 4已有候选待完整验证；3明确有源码/接线缺口；2真实当前硬件状态未判定 | Bluetooth OOB实际controller/peer/别名及可选randomizer；真正peer资源owner和会话；VPN未支持options；重测Bluetooth控制器、USB UDC/MTP。 |
| 定位（9，归location） | 8个API已有路由；1广义backend待全面判定 | 实际provider/轨迹/围栏/行政区、权限/取消；CFI编译、实际镜像/loaded DSO身份与有限路径验证工具接入。不能将单项静态inventory当guest通过。 |
| 电话（13，归location） | 6个RTT listener已修；4个RTT操作原有实现且phone gates已接；2个通信状态生产/observer链已接；1广义radio/SIM/IMS仍需实证 | 真实modem/SIM/IMS/RTT peer、payload、session、监听注销静默、权限/退出；不能把phone开关推广为六包全部通过。 |
| 系统 / 内核（11） | Calendar/Knowledge两项有关键修复；其余5项有实质修复和active接线，3项未见对应provider/model/产品配置修复，1项有真实fallback但行为待判 | GetEvents候选原生验证和build接线；Calendar CRUD与现行提醒viewer整合；Knowledge非空analysis/账号隔离；Ads/OEM DeviceAttest/SecurityGuard真实配置；AppDomain路由。MSDP relativeStill仍明确不支持，原广义ID不因此新增计数。 |
| 媒体（6） | 3项有直接修复待新包完整验证；2项基础管线部分实现；1项AudioVivid插件现状待查 | 采集/录制/编解码/输出真实数据；AudioHaptic当前PCM/VDI与三UID焦点方案衔接、真实onset anchor；AudioVivid真实插件/元数据；广义视频管线。 |

## 本次补回内容仍有哪些整合边界

- Settings选择器：候选已经写过，现已归入分支；旧installer锁定过时Share两文件SHA，当前guard/build/system参数尚未承接，不能直接在产品源上执行旧installer。
- Calendar：旧通用浏览/CRUD候选与现行提醒viewer改写相同上游文件，需正式组合；当前viewer继续启用。GetEvents native寿命候选没有active build调用，需原生/CFI/13个queue caller及环境退出验收。
- AudioHaptic：新旧TIME协议不能局部混用；旧三UID coordinator需要迁移到当前BMS/AccessToken身份和资源owner协议，其原设计因缺真实onset anchor固定不登记通过。
- 网络peer：两QEMU共享Ethernet候选已补回并增加可选packager hooks，仍缺独占VM owner和实际会话验收；Docker OpenVPN peer仍是另一路，不能互相替代。

## 验收顺序

已完成本次整合的155项主机回归、7项分工校验及packager语法检查。没有新包/虚机通过结论。
把已知源码问题合批后，由root构建一个新ARM64 phone代表包，记录包路径、SHA、环境、
命令和正常/边界/回归结果。收齐该轮失败再统一修复；新代表包完整运行gate通过前，
不启动其余五包。先前17-06包是旧源码，不能替代当前分支新包验收。

五个方向继续在同一分支工作，文件编辑范围由root明确分配；共享脚本、Git提交和
source/out、SDK/签名、Docker、VM/HDC/QMP由root串行管理。当前未授予新的产品写入lease。
