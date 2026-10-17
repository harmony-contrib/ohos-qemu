# AudioHaptic 新包专用 QA 工具交接

本轮只新增指定 `batch_media_audio_haptic_*.py`、`audio_haptic_runtime/` fixtures 与
本目录文件。未修改原 AudioHapticProbe、生产补丁、共享 runner/ledger/scripts；没有
git add/commit、Docker/source/out读取、SDK/HAP编译、产品编译、VM或重包操作。
root冻结基线为 `97f58dba86c3ae20f3867048dbbd685b9b463f55`。本轮是未运行的新工具，
此前原API类的惰性SDK105编译不代表此UI宿主或sampler已编译。

## 可运行内容

- `batch_media_audio_haptic_project.py`：生成fresh随机双声道PCM、4秒WAV、真实格式
  时间效果、坏WAV/JSON、两个普通UI工程、完整source manifest和fresh操作nonce。
- `batch_media_audio_haptic_build_callers.py`：root运行的真实SDK105双工程构建器，
  使用实际Node/OHPM/Hvigor及已有私有cache，不下载SDK。保留失败、source_files、
  完整unsigned HAP与可直接用于验收的project-inputs.json；unsigned HAP不算运行通过。
- `batch_media_audio_haptic_build_sampler.py`：在当前进程扩展既有真实CFI helper builder
  配置，读取真实VDI/AccessToken的GN flags、headers/proxy与最终DSO，写独立私有输出。
  --plan-only也只能由root在实际source/out只读租约中执行。未编辑共享builder。
- `batch_media_audio_haptic_runtime.py`：在既有新归档owned guest中，精确普通签名、
  独立Java/CMS验签、安装/BMS/token/HAP读回、私有输入SHA读回、实际UITest节点点击、
  同PID/starttime持久实例、QMP WAV输出、只读HDI/clock采样及真实自有状态清理。
- `batch_media_audio_haptic_verify.py`：重读原始HDC/UITest/SDK/签名/日志/PCM/HDI，
  固定覆盖不能由输入report缩窄；独立输出只表示限定范围行为，始终不关ledger或包门。
- `batch_media_audio_haptic_host_checks.py`：仅受控host结构/协议和反例检查。

固定74个UI操作、36个操作采集区间，再加最终cleanup静默区间。覆盖normal模式
Stop→Start三轮、EOS→Start两轮、两周期以上loop、release/recreate/运行中release、
post-release start、muteAudio/muteHaptics三种组合、坏WAV/坏JSON/缺文件后的合法重试、
独立无VIBRATE普通caller。`project.py plan`给出全部参数和固定预期；故障不是skip。
工具不自动杀音频或振动服务。坏资源后的重试覆盖准备失败，不等同于已经注入
真正StartSound即时失败或音频服务死亡；这两项仍由root另行隔离设计/执行。

## 真实格式和调用来源

miscdevice的公开固定提交 `248a21a014a0794fc8d1853387d139f815df9a56`与本仓库
source lock完全一致，真实文件字节/URL/SHA/许可保存在fixture的upstream目录。
使用原始`oh_no_curve_sample.json`结构，只将continuous事件StartTime从100改0、
Duration从1200改4000；其余Version/ChannelNumber/Index/Intensity/Frequency保留。
真实[DefaultVibratorDecoder](https://raw.githubusercontent.com/openharmony/sensors_miscdevice/248a21a014a0794fc8d1853387d139f815df9a56/utils/haptic_decoder/oh_json/src/default_vibrator_decoder.cpp)
检查这些字段和duration 0..5000；真实[TransformTime](https://raw.githubusercontent.com/openharmony/sensors_miscdevice/248a21a014a0794fc8d1853387d139f815df9a56/services/miscdevice_service/haptic_matcher/src/custom_vibration_matcher.cpp)
产生相邻event-start延时及末尾零时stop marker。这里只证明来源/格式方向；实际新包
decoder→createPlayer→VDI成功必须由真实运行取得，没有预写解码成功receipt。

UI宿主直接复制已有、曾真实SDK105编译的`AudioHapticProbe.ets`原始字节。Index只在
真实按钮`audio_haptic_run`被点击后读取私有request，第一次点击创建probe，此后保留
同一实例；没有生命周期自动执行。实际原始日志为`audio-haptic-RUN.jsonl`，包含
UID/token、boot/run/operation/player_epoch、API返回/BusinessError及真实两个callback。
普通caller声明VIBRATE，denied caller不声明；两个均normal APL、hos_normal_app、空ACL、
空restricted-permissions。VIBRATE是system-grant，工具不执行grant或伪造用户对话框。

QMP语法依据保留的[QEMU v9.0.0主源](https://raw.githubusercontent.com/qemu/qemu/v9.0.0/audio/audio-hmp-cmds.c)，
运行时仍检查实际`help wavcapture`、音频backend ID、ES1370及`info capture`输出。
只启动/停止本工具的新capture 0；若已有其他capture或ownership改变立即失败，
不会stop别人的capture。原主动`vibrator_hdi`探针禁止并发。

## root执行命令

以下路径均为独立QA输出；使用Pillow可用的现有host venv。目录必须fresh，HMP WAV
输出路径目前要求不含空格。root自行等全构建/重包与资源租约，不在构建中运行这些步骤。

```sh
TASK_QA=/Volumes/PSSD/qemu/validation/first-20261005/audio-haptic-NEW-RUN
TASK_PY=/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python
TASK_SDK=/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0
$TASK_PY ci/capability-audit/batch_media_audio_haptic_project.py challenge --output "$TASK_QA/challenge"
$TASK_PY ci/capability-audit/batch_media_audio_haptic_project.py project --role normal --challenge "$TASK_QA/challenge/challenge.json" --sdk "$TASK_SDK" --output "$TASK_QA/normal"
$TASK_PY ci/capability-audit/batch_media_audio_haptic_project.py project --role denied --challenge "$TASK_QA/challenge/challenge.json" --sdk "$TASK_SDK" --output "$TASK_QA/denied"
```

root读取真实可执行路径再传参。下列cache可用旧`r53-AudioHaptic-SDK105-01/hvigor-home`
的已有私有成功material；构建器复制到新输出，避免改共享cache。所有SDK命令会实际执行，
依赖缺失或checker错误保留失败，不会生成“编译通过”的替代结果。

```sh
$TASK_PY ci/capability-audit/batch_media_audio_haptic_build_callers.py \
  --normal "$TASK_QA/normal" --denied "$TASK_QA/denied" --sdk "$TASK_SDK" \
  --node /absolute/actual/node --ohpm /absolute/actual/ohpm/bin/pm-cli.js \
  --hvigor /absolute/actual/6.x/hvigor/bin/hvigorw.js \
  --hvigor-cache /absolute/retained/private/hvigor-home \
  --output "$TASK_QA/sdk-build"
```

如实际OHPM需要保留的私有cache，显式加`--ohpm-cache /absolute/retained/ohpm-home`。
固定离线registry、每个owned Node进程发现最多2 CPU、内存2048MiB、无daemon/parallel。
超时仅终止该构建器自己新建的进程组，继续保留另一角色结果；没有安装/更新工具链。

sampler root构建（在现有Linux只读source/out容器和repo只读挂载内执行）：

```sh
python3 /work/ci/capability-audit/batch_media_audio_haptic_build_sampler.py \
  --source-root /ohos --output /evidence/helpers
```

必须使用该完整产品CFI builder，不可用NDK/__n1、手工disable-CFI或伪造receipt。
实际IDL/graph路径若不同，构建器失败并保留证据，由root集中修复工具。
sampler只提供clock/token/sample；sample仅调用V2_0 `IsVibratorRunning({0,0})`，
不含Start/Stop/Enable/Play/Grant/Revoke。独立token查询两角色真实VIBRATE。

`artifacts.json`的精确结构如下，所有descriptor为实际绝对path及SHA256。projects直接
使用SDK构建输出project-inputs.json，不能用旧inert HAP。signer采用现有固定公开QA签名
distribution/jar；helper output_directory是实际host保留目录，build指原始不可改写receipt。

```json
{
  "schema_version": 1,
  "challenge": {"path": "/absolute/challenge/challenge.json", "sha256": "ACTUAL"},
  "projects": {"normal": "USE_FULL_NORMAL_OBJECT_FROM_project-inputs.json", "denied": "USE_FULL_DENIED_OBJECT"},
  "signer": {"dist": "/absolute/retained/signer/dist", "jar": {"path": "/absolute/hap-sign-tool.jar", "sha256": "ACTUAL"}},
  "helper": {
    "build": {"path": "/absolute/helpers/build.json", "sha256": "ACTUAL"},
    "output_directory": "/absolute/helpers",
    "path_map": {"/work": "/Volumes/PSSD/code/ohos-rs/ohos-qemu", "/evidence/helpers": "/absolute/helpers"}
  }
}
```

projects示意字符串必须换成完整对象，字段为sdk_evidence、sdk_project、source_project、
source_manifest、unsigned_hap。运行套件不接受字符串、缺字段或借旧HAP的输入。
也可直接用下列生成器代替手填descriptor/SHA。`helper-path-map.json`是上例path_map
对象；只映射两个明确原始前缀，不改写任何原始build receipt。

```sh
$TASK_PY ci/capability-audit/batch_media_audio_haptic_project.py artifacts \
  --challenge "$TASK_QA/challenge/challenge.json" --projects "$TASK_QA/sdk-build/project-inputs.json" \
  --signer-dist /absolute/retained/signer/dist --jar /absolute/hap-sign-tool.jar \
  --helper-build /absolute/helpers/build.json --helper-output /absolute/helpers \
  --helper-path-map "$TASK_QA/helper-path-map.json" --output "$TASK_QA/artifacts.json"
```

新包真实owned acceptance guest启动后（套件自己不启动/停止VM）：

```sh
$TASK_PY ci/capability-audit/batch_media_audio_haptic_runtime.py \
  --archive /absolute/NEW-arm64-phone.tar.gz --boot /absolute/NEW-acceptance-boot/evidence.json \
  --artifacts "$TASK_QA/artifacts.json" --hdc /absolute/actual/hdc \
  --exclusive-audio-vibrator --output "$TASK_QA/runtime"

$TASK_PY ci/capability-audit/batch_media_audio_haptic_verify.py \
  --archive /absolute/NEW-arm64-phone.tar.gz --boot /absolute/NEW-acceptance-boot/evidence.json \
  --evidence "$TASK_QA/runtime/evidence.json" --output "$TASK_QA/independent-recheck"
```

boot必须符合既有EnclosingAcceptanceGuest的未更换镜像/QMP/PID/boot/UDID契约。签名在
这台真实guest UDID确定后才执行；实际BMS的普通身份、唯一路径安装HAP和字节读回均重验。
root需排除同guest其他音频/振动producer及主动HDI probe；套件另持同guest文件锁。

## 原始观测、失败和清理

每次操作独立生成nonce，root原子发布request到实际UID的0600 filesDir文件，再按
真实UITest hierarchy的可见/可点击节点及compositor截图点击；不猜坐标。每次记录
boot/PID/kernel starttime，PID或starttime改变就失败，不把新对象当原实例。
API预计失败仍保留真实terminal error并继续固定后续步骤；超时/传输/格式等异常退出
行为收集，finally仍尝试收齐已有journal/token、public stop/release、自有HAP卸载与
PID/AMS/BMS/私有文件缺失、最终独立音频/VDI静默及helper/UI文件移除。

只读sampler通过该run root私有stop文件退出。若IPC卡死，仅在真实exe/PID/starttime
全部仍匹配时TERM本工具自己的observer；不杀任何音频/振动服务。不能证明observer
退出时保留相关文件并将cleanup失败，绝不删除其他人的effect或停整个VM。
清理任何一步失败都使套件失败，保留failure/cleanup_errors和所有已有命令/日志。

音频独立使用QEMU宿主输出，不从HAP自己的WAV或自报状态判定成功。随机双声道
reference逐窗口相关性/声道隔离/采样位移、4秒EOS、loop尾部及静默边界均重算。
0帧或空文件不能证明静默。HDI raw每次保留返回值、实际running与单调/实时采样时间；
非零返回、超过200ms的采样间断、或不足够tail样本均失败。guest/host monotonic通过
前后实际clock进程调用做区间校准，交集不一致或宽于400ms则不宣称同步。

## 必须保留的未验证项

1. 这批新Index UI、双HAP build脚本、sampler C++、实际GN/CFI/proxy/最终链接均未执行。
   只做了5项host结构/协议反例检查；原类旧unsigned HAP成功不能替代新UI工程编译。
2. 74步真实UI/签名/安装/权限/音频/VDI/cleanup首次运行均未验证，BusinessError具体码、
   HMP文字格式、实际WAV decoder或VDI路径差异会保留为真实失败，不能skip。
3. QMP WAV在当前实际音频backend静默时是否持续输出带时钟的0样本尚不确定。
   工具要求捕获时长与宿主时长相差不超过250ms，空/暂停时钟会明确失败。需要root
   根据实际QEMU证据补独立capture时钟适配，不能把“没有样本”降低成静默通过。
4. onset比较保留实际校准区间及250ms capture-frame原点不确定性，检查200ms加
   测量不确定性范围；不声称物理马达、DSP级同步精度或HD/intensity/frequency能力。
5. 公开API没有first-frame callback。真实hilog原样保存，但日志每轮freshness尚无独立
   native nonce绑定，结果明确first_frame_native_log_freshness_verified=false。
   原生产DSO的compile→image witness仍由root整体构建证据提供；这批独立绑定sampler
   的真实产品DSO/CFI和运行maps，不替root生成媒体生产库构建见证。
6. 跨轮迟到first-frame在下一轮rearm后才到达的生产缺口未修；静默/重启测试用于
   暴露它，始终cross_generation_callback_gap_closed=false。完整双UID焦点协议仍独立。
7. 所有七条ledger仍open；即便限定runtime工具通过，也不设置first-artifact门或启动
   其余五包。归档path/SHA、环境、命令和实际结果由root与代表新包证据统一保存。

host命令与原始输出保存在`host-checks.log`；机器交接为`result.json`。测试输出只代表
受控host结构和oracle反例，不包含伪造的guest journal/VDI/成功receipt。
