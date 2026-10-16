# 82条未核销要求：下一轮可执行交付清单

只读基点为 root 已提交的 `43a4c43991d3a5a9fe60c50c302d10daae592f99`。
权威集合是 `parallel-work-plan.json` 的五组 requirements，恰好82个唯一ID：
apps34、network9、location22、media7、system10。原账目仍是281要求、199已关、
82未关；本报告不修改账本，不新增核销，六包完整接受仍0/6，首包门禁仍false。

| 主类 | ID数 | 含义 |
| --- | ---: | --- |
| A：已有修复候选，待新包运行 | 25 | 已有可供实际运行验证的源码方向；不代表全部子功能或运行工具已完整，更不代表通过 |
| B：尚缺实现或接线，可继续仓库修复 | 23 | 已交资料明确指出仍缺真实入口、客户端、格式处理或产品接线，不能只等一遍编译 |
| C：真实供应方/硬件/凭据/对端数据仍缺 | 30 | 缺实际可工作的provider、输入或peer；多项可自主部署受控软件端，不等于30项都要用户提供材料 |
| U：证据不足，待核查 | 4 | 先补根因/新包差分，不能猜成“已修好”或“必须采购” |

[OPEN_ITEMS.md](OPEN_ITEMS.md) 是逐条82行的可读交付表；
`open-items.json` 保存相同ID、唯一owner、主类、下一步、证据、未知项及原agent快照。
每个ID只出现一次。`work-packages.json` 将共用工作归为59个协调索引，
并列跨包依赖；这59不是新增缺陷数，也不等于59份互不依赖的代码修改。
三个VPN记录共用broker、十个RTT导出共用IMS、BLE导出共用HCI，不能分别计算一次
独立后端工程。聚合导出、广义MSDP、定位provider和媒体依赖管线也不能因为
若干子条目通过而整体核销。

## 本次已纠正的陈旧交接

- **Knowledge已有正式数据和转发修复。** root `b1aa03c` 已加入
  `patches/resources/knowledge/cn-2026/{holidays.ics,provenance.json}`，launcher
  现在有真实只读bind和 `QEMU_KNOWLEDGE_ICS` 转发。不应重派round16旧接线问题，
  也不应要求用户提供CN/2026 ICS。正式asset SHA是
  `12798eab4471df83e23359ace64cab99228a256763cda188db5ded01ed32dfc9`，
  与旧docs候选只差PRODID的candidate标记；`provenance.asset`正确绑定正式字节。
  还需实际producer、镜像输入选择、真实照片日期和公开权限/帐号结果。其范围只含
  官方2026通知的七段休假安排，不含全球日历、补班日或其他年份。
- **壁纸已有真实UI方向。** media round11已实现Settings选择/预览/set/restore，
  并有真实native fallback及后续连接/图像/归档重放工具。Apps旧累计result的
  “设置UI仍缺”已陈旧。实际BMS、URI权限、持久图像和屏幕仍待新包证明；
  不扩大声称所有live wallpaper/ThemeService接口都已实现。
- **MSDP当前15个产品TU已有覆盖。** committed coverage receipt的manifest SHA
  与当前 `public_still/manifest.json`完全一致。旧“再重编全部15”不是当前待办。
  仍缺新GN/完整DSO链接与实际普通API运行；独立still实例只覆盖既有五事件加速度
  启发式，不能证明物理静止精度，relativeStill等广义客户端仍未完成，所以此ID为B。
- **Calendar已有Editor。** 真实EditorUIExtension源组件已交，不再按“完全缺editor”
  派同一修复。完整Calendar MainAbility/提醒URI和提醒/CRUD/重启仍是不同工作。
- **图形保护不混称。** child及部分系统DSO有CFI证据；两个3D原目标仅选择LTO。
  已有TU/链接或QEMU-user ABI消费端结果都不能冒充完整新guest运行通过。

## 七类重点供应/输入边界

完整契约、finding对应关系和操作动作见 `external-dependencies.json`。
`material-inventory.json`保存固定commit下的文件名和精确内容引用检索。
没有读取外部私有artifact缓存、凭据库、Docker、source/out或互联网；
“未在当前已提交资料识别到可部署合法材料路径”不能外推为所有环境都没有。

| 能力族 | 已确认缺口 | root可执行的下一步与材料边界 |
| --- | --- | --- |
| OEM Attest | 固定OEM产品ID/key为空，没有已交合法provisioning | 向授权OEM取得产品登记、身份/key安全provisioning及真实验证服务/信任链。通用平台签名、随机ID/key不等价。只交材料引用，不把secret贴入报告 |
| AudioVivid | loader/factory ABI存在，没有真实metadata格式实现/许可/artifact | 识别合法源码/SDK及规范，核factory/destructor和构建再集成；真实位置/增益metadata独立往返。不能用JSON或固定bytes替代，也不能凭本仓库搜索宣称外界不存在开源实现 |
| Ads | sample provider未交付，配置还缺真实API入口 | 先指定可工作的provider及合法内容/服务和remote/JS/UI协议，再填配置/签名安装。可自主做真实发布后端，但demo空结果不能成为业务广告材料 |
| SecurityGuard | `modelcfg=[]`，没有定义并实现的产品模型 | 先明确真实modelName、事件/collector和有意义输出语义，再复核引擎schema/ABI及规则/模型材料。现有证据不证明必须商业OEM插件 |
| IMS/modem | 有参考AT/RIL和IMS消费者，没有实际运行peer | 可自主做受控虚拟AT tty/state machine和真实IMS服务/peer，走完整协议链；只有声称真实运营商互通时才需商业SIM/网络provisioning。AT注册不等于RTT |
| HCI | 有OOB/GAP和BLE逻辑，没有实际vendor-H4-controller/peer | 自主接合法受控虚拟controller或真实passthrough；H4命令事件必须经Bluetooth栈。实际配对、C/R、数据和off/unplug不能由直接上层回调证明 |
| geocoder | 有真实Binder ABI，无provider及合法实际行政区数据 | 可自主研究合法公开多边形/真实服务并实现空间查询；不先天要求商业地图key。有限测试polygon或固定区名不能当正式行政区资料 |

SecurityGuard还有一个具体审计边界：`build_hap_probe.py:1373`查询的是任意
`modelName: 'capability-audit'`。未知模型返回401本身不是所有合法模型都坏的证据。
真实缺口依据是空的产品模型配置与没有已交有意义实现；下一步必须先选真实产品
模型并验证实际输入，不能把401改成空成功。这个测试名字也不是现成业务模型。

其余C类还包括真实WiFi/AP peer、USB设备/UDC、cast/分布式peer和合法号码业务数据。
受控peer可由root自主部署；外部硬件、私有数据或商业服务才相应需要授权材料。
没有足够证据时，字幕ASR、翻译/实体识别模型来源保留为对应B项的待核查条件，
不新增一个未经证实的“必须购买模型”阻塞。

## 四个U项先做什么

1. `behavior:api26-runtime-export-mismatches-phone`：新归档重采实际导出，按模块列
   仍缺的成员/值/调用行为，引用已有修复去重；不从旧聚合40个syscap猜当前剩余数。
2. `behavior:intelligent-scene-notification-query-fails`：真实新包分别复测两种DND
   查询并记录provider初始化/协议/权限/重启，才决定改哪层。
3. `behavior:certificate-dialog-device-result`：沿真实certificate_manager支持判断
   检查UI、选择/取消/空列表/device分支；已存在真实扩展，旧false不是缺HAP结论。
4. `behavior:app-domain-verification-extension-missing`：已有真实VerifyTask fallback，
   先用可控HTTPS association与真实签名匹配/不匹配bundle验证refresh/cache/路由；
   仅在empty TargetInfo确实导致失败时修选包，不能因为可选so缺失就猜整个验证坏。

## root下一轮执行顺序

1. 完成当前已运行的有界GN工作并保留其证据，不改这次冻结输入。本报告只写文档，
   不持heavy lease，不触碰共享builder、suite、策略或账本。
2. 按B类及C类的实际已选产品范围分派源码/数据/peer工作；共享源继续唯一owner。
   一份共用实现只排一次，逐ID的行为断言仍必须分别满足。把已知实现、材料和运行
   工具缺口集中修完，再启动下一次代表包构建；不为单个条目循环整包。
3. 真实代表归档存在后，root以实际预构建输入计划运行当前正式入口；以下仅为将来
   的命令模板，本次没有执行：

   ```sh
   QEMU_TEST_CAPABILITY_INPUTS=/ABS/current-capability-inputs.json \
     python3 ci/capability-audit/run_packaged_qemu_suite.py \
       --package-archive /ABS/new-arm64-phone.tar.gz \
       --evidence-output /ABS/private-first-artifact-evidence.json
   ```

   运行前仍须满足该工具实际SDK/签名/依赖/对端环境和唯一重资源调度，不是只填
   三个路径即可。同VMfamily失败后的复用必须以真实cleanup结果决定。完整保留
   尝试与可安全取得的独立失败，不因第一个UI错误而把其他要求写成已通过。
4. 对实际归档/boot原字节重新执行严格总验收：

   ```sh
   python3 ci/capability-audit/verify_gap_closure.py \
     --archive /ABS/new-arm64-phone.tar.gz --boot /ABS/work/boot/boot.json \
     --runtime-root /ABS/work --device phone --output /ABS/recomputed-gaps.json
   ```

   A类不是自动核销25项；需要对应完整行为证据和正式验证器登记。当前新增三family
   的closure映射只允许Contacts和Wallpaper各一个精确ID；external-inputs明确不核销
   广义MSDP。不得把本表分类、成功编译、旧image或host模型当作closure证据。
5. R50 HiTrace和R51 RenderService sleep/wake是原82以外的两个核心验收故障，单列
   跟踪，不重复加到82。已有suspend-aware参数候选仍需新guest双时钟和sleep/wake，
   并保留正常awake watchdog反例；不能延长超时或绕过RS健康门禁。首包完整实际行为
   门禁通过后才构建其余五包，并逐架构/画像验收。

`source-evidence.json`锁定本次读过的已提交材料；`check-results.json`只记录轻量
JSON、集合/哈希和docs scope检查。本次没有新的native/SDK/VM/运行通过声明。
